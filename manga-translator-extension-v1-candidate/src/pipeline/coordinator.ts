import { AppError, serializeError } from '../core/errors.js';
import type { AcquisitionHandoffStore } from '../core/background-acquisition.js';
import type { SessionStore, StoredPageSession } from '../core/session-store.js';
import type { AcquiredImage, AcquisitionFailure } from '../page/types.js';
import { newJobId, workIdFromSignature } from '../shared/ids.js';
import type { RuntimeSessionStore } from '../state/runtime-session.js';
import type { BinaryStore } from '../binary/binary-store.js';
import { browser } from 'wxt/browser';
import { sendMessage } from '../messaging/protocol.js';
import { DEFAULT_PROCESSING_SPEC, deriveWorkSignature, processingSpecFingerprint, validateProcessingSpec } from './processing-spec.js';
import { sha256Blob } from './sha256.js';
import type {
  CancellationKind,
  JobRecord,
  PageTranslateOutcome,
  PipelineStartResult,
  ProcessingSpec,
  WorkRecord
} from './types.js';
import { validatePipelineResult, validatePipelineSource } from './source-validation.js';
import { isTerminalJobStage, type JobStore } from './job-store.js';
import type { LocalProcessingGateway } from '../engine/local-processing-gateway.js';
import type { EngineJobStatus } from '../engine/types.js';
import { isJobFreshForDelivery } from './delivery-gate.js';
import { WorkStore } from '../queue/work-store.js';
import { CandidateAdmissionScheduler } from '../queue/candidate-admission.js';
import { AsyncLane } from '../queue/capacities.js';
import { MemoryAdmissionController } from '../queue/memory-admission.js';
import { buildSchedulingHint, compareJobs } from '../queue/priority.js';
import { ResultCache } from '../cache/result-cache.js';
import { deriveResultCacheKey } from '../cache/cache-key.js';
import { RetryWakeScheduler } from '../queue/retry-wake.js';
import { effectiveLocale } from '../ui/i18n.js';
import { UiSettingsStore } from '../ui/settings.js';
import { ENGINE_DURABLE_RECHECK_MS, ENGINE_POLL_GRACE_MS, ENGINE_POLL_INTERVAL_MS, MAX_WORK_CONSUMERS, QUEUE_WAKE_ALARM } from '../shared/constants.js';

export type QueueWakeReason = 'request' | 'intake' | 'startup' | 'alarm' | 'reconcile' | 'snapshot';

export type QueueSnapshot = {
  pageSessionId: string;
  active: Array<{
    jobId: string;
    candidateId: string;
    stage: JobRecord['stage'];
    priorityBand: JobRecord['schedulingHint']['priorityBand'];
    workId?: string;
    cacheHit?: boolean;
    engineStage?: string;
    progress?: { completed: number; total: number };
  }>;
  recentTerminal: Array<{
    jobId: string;
    candidateId: string;
    stage: JobRecord['stage'];
    errorCode?: string;
  }>;
  cache: { approxBytes: number; approxEntries: number };
  nextWakeAt: number | null;
};

export class PipelineCoordinator {
  readonly #sessions: SessionStore;
  readonly #runtimeSessions: RuntimeSessionStore;
  readonly #jobs: JobStore;
  readonly #works: WorkStore;
  readonly #binaries: BinaryStore;
  readonly #acquisitions: AcquisitionHandoffStore;
  readonly #gateway: LocalProcessingGateway;
  readonly #cache: ResultCache;
  readonly #admission = new CandidateAdmissionScheduler();
  readonly #memory = new MemoryAdmissionController();
  readonly #acquisitionLane = new AsyncLane(2);
  readonly #hashLane = new AsyncLane(1);
  readonly #engineLane = new AsyncLane(1);
  readonly #resultLane = new AsyncLane(1);
  readonly #deliveryLane = new AsyncLane(2);
  readonly #retryWake = new RetryWakeScheduler();
  readonly #uiSettings: UiSettingsStore;
  readonly #acquisitionFailures = new Map<string, AcquisitionFailure>();
  #pumpPromise: Promise<void> | null = null;
  #reconcileTail: Promise<void> = Promise.resolve();

  constructor(options: {
    sessions: SessionStore;
    runtimeSessions: RuntimeSessionStore;
    jobs: JobStore;
    binaries: BinaryStore;
    acquisitions: AcquisitionHandoffStore;
    gateway: LocalProcessingGateway;
    works?: WorkStore;
    cache?: ResultCache;
    uiSettings?: UiSettingsStore;
  }) {
    this.#sessions = options.sessions;
    this.#runtimeSessions = options.runtimeSessions;
    this.#jobs = options.jobs;
    this.#binaries = options.binaries;
    this.#acquisitions = options.acquisitions;
    this.#gateway = options.gateway;
    this.#works = options.works ?? new WorkStore();
    this.#cache = options.cache ?? new ResultCache();
    this.#uiSettings = options.uiSettings ?? new UiSettingsStore();
  }

  /** Preferred Phase 3 path: background owns admission before asking the page to acquire bytes. */
  async requestTranslation(input: {
    session: StoredPageSession;
    candidateId: string;
    sourceRevision: number;
    allowScreenshot: boolean;
    processingSpec?: ProcessingSpec;
  }): Promise<PageTranslateOutcome> {
    const candidate = input.session.candidates[input.candidateId];
    if (!candidate) return acquisitionFailure(input.candidateId, 'CANDIDATE_NOT_FOUND', 'Candidate is not part of the current PageSession.');
    if (!input.session.documentId) return acquisitionFailure(input.candidateId, 'STALE_DOCUMENT', 'PageSession has no active document identity.');
    if (candidate.sourceRevision !== input.sourceRevision) return acquisitionFailure(input.candidateId, 'STALE_TARGET', 'Candidate source changed before queue admission.');

    const job = await this.#createJob({
      session: input.session,
      candidateId: input.candidateId,
      sourceRevision: input.sourceRevision,
      allowScreenshot: input.allowScreenshot,
      explicit: true,
      ...(input.processingSpec ? { processingSpec: input.processingSpec } : {})
    });
    await this.pump('request');
    const acquisitionProblem = this.#acquisitionFailures.get(job.jobId);
    this.#acquisitionFailures.delete(job.jobId);
    if (acquisitionProblem) return { ok: false, failure: acquisitionProblem };
    const final = await this.#jobs.get(job.jobId);
    if (!final) return acquisitionFailure(input.candidateId, 'JOB_NOT_FOUND', 'Queue job disappeared unexpectedly.');
    return { ok: true, result: resultFromJob(final) };
  }

  async enqueuePageTranslations(input: {
    session: StoredPageSession;
    processingSpec: ProcessingSpec;
    allowScreenshot: boolean;
  }): Promise<{ queued: number; skippedFar: number; rejected: number; jobIds: string[] }> {
    validateProcessingSpec(input.processingSpec);
    const candidates = Object.values(input.session.candidates)
      .sort((a, b) => (a.orderHint ?? Number.MAX_SAFE_INTEGER) - (b.orderHint ?? Number.MAX_SAFE_INTEGER) || a.candidateId.localeCompare(b.candidateId));
    const jobIds: string[] = [];
    let skippedFar = 0;
    let rejected = 0;
    for (const candidate of candidates) {
      if ((candidate.visibility ?? 'far') === 'far') {
        skippedFar += 1;
        continue;
      }
      try {
        const job = await this.#createJob({
          session: input.session,
          candidateId: candidate.candidateId,
          sourceRevision: candidate.sourceRevision,
          allowScreenshot: input.allowScreenshot,
          explicit: false,
          processingSpec: input.processingSpec
        });
        jobIds.push(job.jobId);
      } catch {
        rejected += 1;
      }
    }
    if (jobIds.length > 0) await this.pump('request');
    return { queued: jobIds.length, skippedFar, rejected, jobIds };
  }

  /** Compatibility path for Phase 2 content-script intake. New UI uses requestTranslation(). */
  async start(input: {
    session: StoredPageSession;
    candidateId: string;
    sourceRevision: number;
    acquired: AcquiredImage;
  }): Promise<PipelineStartResult> {
    const candidate = input.session.candidates[input.candidateId];
    if (!candidate) return failureResult('', 'CANDIDATE_NOT_FOUND');
    if (!input.session.documentId) return failureResult('', 'STALE_DOCUMENT');
    if (candidate.sourceRevision !== input.sourceRevision || input.acquired.candidateId !== input.candidateId) {
      return failureResult('', 'STALE_TARGET');
    }
    const job = await this.#createJob({
      session: input.session,
      candidateId: input.candidateId,
      sourceRevision: input.sourceRevision,
      allowScreenshot: false,
      explicit: true
    });
    const acquisitionId = input.acquired.acquisitionId;
    try {
      await this.#stageAcquired(job.jobId, input.acquired);
      await this.pump('intake');
      return resultFromJob((await this.#jobs.get(job.jobId)) ?? job);
    } catch (error) {
      return await this.#failJob(job.jobId, error);
    } finally {
      if (acquisitionId) this.#acquisitions.release(acquisitionId);
    }
  }

  async pump(reason: QueueWakeReason): Promise<void> {
    if (this.#pumpPromise) return await this.#pumpPromise;
    const operation = this.#runPump(reason);
    const wrapped = operation.finally(() => {
      if (this.#pumpPromise === wrapped) this.#pumpPromise = null;
    });
    this.#pumpPromise = wrapped;
    await wrapped;
  }

  async reconcile(): Promise<void> {
    const operation = this.#reconcileTail.then(async () => {
      const runtime = await this.#runtimeSessions.getOrCreate();
      await this.#binaries.reconcileRuntimeSession(runtime.runtimeSessionId);

      const duplicateMap = await this.#works.reconcileDuplicateSignatures();
      if (duplicateMap.length) {
        const jobs = await this.#jobs.listNonTerminal();
        for (const merge of duplicateMap) {
          for (const job of jobs.filter((item) => item.workId === merge.duplicateWorkId)) {
            await this.#jobs.update(job.jobId, (draft) => {
              draft.workId = merge.canonicalWorkId;
              draft.stage = 'joined-work';
            });
          }
          await this.#binaries.releaseOwner('work', merge.duplicateWorkId).catch(() => undefined);
        }
      }

      const jobs = await this.#jobs.list();
      for (const job of jobs) {
        if (job.runtimeSessionId !== runtime.runtimeSessionId) {
          if (!isTerminalJobStage(job.stage)) {
            await this.#jobs.update(job.jobId, (draft) => {
              draft.stage = 'cancelled';
              draft.cancellationKind = 'session-close';
              draft.lastErrorCode = 'STALE_SESSION';
            });
          }
          await this.#binaries.releaseOwner('job', job.jobId).catch(() => undefined);
          continue;
        }
        if (isTerminalJobStage(job.stage)) {
          await this.#binaries.releaseOwner('job', job.jobId).catch(() => undefined);
          continue;
        }
        if ((job.stage === 'staging-source' || job.stage === 'hashing') && !job.source) {
          const recovered = await this.#binaries.findOwnedBinary('job', job.jobId, 'source');
          if (recovered) {
            await this.#jobs.update(job.jobId, (draft) => {
              draft.source = recovered;
              draft.stage = 'hashing';
            });
          } else {
            await this.#jobs.update(job.jobId, (draft) => {
              draft.stage = 'waiting-admission';
            });
          }
        }
        if (job.signature && !job.workId && (job.stage === 'waiting-work' || job.stage === 'joined-work')) {
          const existing = await this.#works.findBySignature(job.signature);
          if (existing) {
            let workSource = await this.#binaries.findOwnedBinary('work', existing.workId, 'source');
            if (!workSource && job.source?.binaryId === existing.sourceBinaryId) {
              await this.#binaries.acquireLease({
                binaryId: job.source.binaryId,
                ownerType: 'work',
                ownerId: existing.workId,
                role: 'source',
                runtimeSessionId: job.runtimeSessionId
              }).catch(() => undefined);
              workSource = await this.#binaries.findOwnedBinary('work', existing.workId, 'source');
            }
            if (workSource) {
              await this.#jobs.update(job.jobId, (draft) => {
                draft.workId = existing.workId;
                draft.stage = 'joined-work';
              });
              if (job.source) {
                await this.#binaries.releaseLease({ binaryId: job.source.binaryId, ownerType: 'job', ownerId: job.jobId, role: 'source' }).catch(() => undefined);
              }
            }
          }
        }
      }

      const works = await this.#works.list();
      for (const work of works) {
        if (work.runtimeSessionId !== runtime.runtimeSessionId) {
          await this.#binaries.releaseOwner('work', work.workId).catch(() => undefined);
          await this.#works.remove(work.workId);
          continue;
        }
        if (work.stage === 'queued' || work.stage === 'submitting' || work.stage === 'processing') {
          let workSource = await this.#binaries.findOwnedBinary('work', work.workId, 'source');
          if (!workSource) {
            const donor = jobs.find((candidate) =>
              !isTerminalJobStage(candidate.stage) &&
              (candidate.workId === work.workId || candidate.signature === work.jobSignature) &&
              candidate.source?.binaryId === work.sourceBinaryId
            );
            if (donor?.source) {
              await this.#binaries.acquireLease({
                binaryId: donor.source.binaryId,
                ownerType: 'work',
                ownerId: work.workId,
                role: 'source',
                runtimeSessionId: work.runtimeSessionId
              }).catch(() => undefined);
              workSource = await this.#binaries.findOwnedBinary('work', work.workId, 'source');
            }
          }
          if (!workSource) {
            await this.#works.update(work.workId, (draft) => {
              draft.stage = 'failed';
              draft.lastErrorCode = 'BINARY_NOT_FOUND';
            });
            continue;
          }
        }
        if ((work.stage === 'fetching-result' || work.stage === 'validating-result') && !work.resultBinaryId) {
          const recovered = await this.#binaries.findOwnedBinary('work', work.workId, 'result');
          if (recovered) {
            await this.#works.update(work.workId, (draft) => {
              draft.resultBinaryId = recovered.binaryId;
              draft.resultEncoderSemantics = 'engine-exact-lossless-v1';
              draft.resultRaster = { pixelWidth: draft.sourceRaster.pixelWidth, pixelHeight: draft.sourceRaster.pixelHeight, ...(draft.sourceRaster.capture ? { capture: draft.sourceRaster.capture } : {}) };
              draft.stage = 'validating-result';
            });
          } else if (!work.engineTicket) {
            await this.#works.update(work.workId, (draft) => {
              draft.stage = 'queued';
            });
          }
        }
        if (!work.processingSpec) {
          const donor = jobs.find((candidate) => candidate.workId === work.workId || candidate.signature === work.jobSignature);
          if (donor) {
            await this.#works.update(work.workId, (draft) => {
              draft.processingSpec = structuredClone(donor.processingSpec);
            });
          } else if (work.stage !== 'ready' && work.stage !== 'failed' && work.stage !== 'cancelled') {
            await this.#works.update(work.workId, (draft) => {
              draft.stage = 'failed';
              draft.lastErrorCode = 'PROCESSING_SPEC_INVALID';
            });
          }
        }
      }

      await this.#cache.evictToBudget().catch(() => undefined);
      await this.#reconcileAlarm();
      await this.pump('reconcile');
      await this.#jobs.removeTerminalOlderThan(Date.now() - 12 * 60 * 60 * 1000);
    });
    this.#reconcileTail = operation.catch(() => undefined);
    await operation;
  }

  async cancelJob(jobId: string, kind: CancellationKind): Promise<void> {
    const job = await this.#jobs.get(jobId);
    if (!job || isTerminalJobStage(job.stage)) return;
    await this.#jobs.update(jobId, (draft) => {
      draft.cancelRequested = true;
      draft.cancellationKind = kind;
      draft.stage = kind === 'navigation-stale' ? 'stale' : 'cancelled';
      if (kind === 'navigation-stale') draft.lastErrorCode = 'STALE_TARGET';
      else delete draft.lastErrorCode;
    });
    await this.#binaries.releaseOwner('job', jobId).catch(() => undefined);
    if (job.workId) {
      const remaining = (await this.#jobs.listNonTerminal()).filter((candidate) => candidate.workId === job.workId && candidate.jobId !== jobId);
      if (remaining.length === 0 && kind === 'explicit-user') {
        const work = await this.#works.get(job.workId);
        if (work) {
          const updated = await this.#works.update(work.workId, (draft) => {
            draft.suppressCachePromotion = true;
            if (draft.engineTicket && draft.stage !== 'ready' && draft.stage !== 'failed' && draft.stage !== 'cancelled') {
              draft.stage = 'cancelling';
              draft.notBefore = Date.now();
            } else if (draft.stage === 'queued') {
              draft.stage = 'cancelled';
            }
          });
          if (updated.engineTicket && updated.stage === 'cancelling') {
            await this.#gateway.cancelJob(updated.engineTicket).catch(() => undefined);
            await this.pump('request').catch(() => undefined);
          }
        }
      }
    }
    await this.#cleanupCompletedWorks();
    await this.#reconcileAlarm();
    await this.#updateActionBadges();
  }

  async snapshot(pageSessionId: string): Promise<QueueSnapshot> {
    const jobs = (await this.#jobs.list()).filter((job) => job.target.sessionId === pageSessionId).sort(compareJobs);
    const workMap = new Map((await this.#works.list()).map((work) => [work.workId, work] as const));
    const cache = await this.#cache.getStats();
    const alarm = await browser.alarms.get(QUEUE_WAKE_ALARM);
    return {
      pageSessionId,
      active: jobs.filter((job) => !isTerminalJobStage(job.stage)).map((job) => {
        const work = job.workId ? workMap.get(job.workId) : undefined;
        return {
          jobId: job.jobId,
          candidateId: job.target.candidateId,
          stage: job.stage,
          priorityBand: job.schedulingHint.priorityBand,
          ...(job.workId ? { workId: job.workId } : {}),
          ...(job.cacheHit !== undefined ? { cacheHit: job.cacheHit } : {}),
          ...(work?.engineStage ? { engineStage: work.engineStage } : {}),
          ...(work?.engineProgress ? { progress: work.engineProgress } : {})
        };
      }),
      recentTerminal: jobs.filter((job) => isTerminalJobStage(job.stage)).slice(-20).map((job) => ({
        jobId: job.jobId,
        candidateId: job.target.candidateId,
        stage: job.stage,
        ...(job.lastErrorCode ? { errorCode: job.lastErrorCode } : {})
      })),
      cache: { approxBytes: cache.approxBytes, approxEntries: cache.approxEntries },
      nextWakeAt: alarm?.scheduledTime ?? null
    };
  }

  async #runPump(_reason: QueueWakeReason): Promise<void> {
    for (let cycle = 0; cycle < 64; cycle += 1) {
      let progressed = false;
      progressed = (await this.#admitWaitingJobs()) || progressed;
      progressed = (await this.#attachHashedJobs()) || progressed;
      progressed = (await this.#processOneWork()) || progressed;
      progressed = (await this.#hydrateJobsFromReadyWork()) || progressed;
      progressed = (await this.#deliverReadyJobs()) || progressed;
      await this.#cleanupCompletedWorks();
      if (!progressed) break;
      await Promise.resolve();
    }
    await this.#reconcileAlarm();
    await this.#updateActionBadges();
  }

  async #updateActionBadges(): Promise<void> {
    const [sessions, jobs] = await Promise.all([this.#sessions.list(), this.#jobs.list()]);
    await Promise.all(sessions.map(async (session) => {
      const scoped = jobs.filter((job) => job.target.sessionId === session.sessionId);
      const hasActive = scoped.some((job) => !isTerminalJobStage(job.stage));
      const hasAttention = scoped.some((job) => job.stage === 'failed');
      const text = hasAttention ? '!' : hasActive ? '…' : '';
      await browser.action.setBadgeText({ tabId: session.tabId, text }).catch(() => undefined);
      const title = hasAttention
        ? `${browser.i18n.getMessage('appName') || 'Manga Translator'} — ${browser.i18n.getMessage('needsAttention') || 'Action required'}`
        : hasActive
          ? `${browser.i18n.getMessage('appName') || 'Manga Translator'} — ${browser.i18n.getMessage('working') || 'Processing'}`
          : (browser.i18n.getMessage('actionTitle') || 'Open Manga Translator');
      await browser.action.setTitle({ tabId: session.tabId, title }).catch(() => undefined);
    }));
  }

  async #admitWaitingJobs(): Promise<boolean> {
    const jobs = await this.#jobs.listNonTerminal();
    const preparedBySession = new Map<string, number>();
    for (const job of jobs) {
      if (job.stage === 'waiting-work' || job.stage === 'joined-work') {
        preparedBySession.set(job.target.sessionId, (preparedBySession.get(job.target.sessionId) ?? 0) + 1);
      }
    }
    const sessions = await this.#sessions.list();
    const activeSessionId = sessions.find((session) => session.status === 'active')?.sessionId;
    const selection = this.#admission.select({
      jobs,
      ...(activeSessionId ? { activeSessionId } : {}),
      acquisitionCapacity: Math.max(0, this.#acquisitionLane.capacity - this.#acquisitionLane.active),
      preparedBySession
    });
    if (selection.admitted.length === 0) return false;
    await Promise.all(selection.admitted.map((job) => this.#acquisitionLane.run(async () => {
      const memory = await this.#memory.reserve(job.schedulingHint.estimatedSourceBytes);
      try {
        await this.#acquireForJob(job);
      } finally {
        memory.release();
      }
    })));
    return true;
  }

  async #acquireForJob(job: JobRecord): Promise<void> {
    const fresh = await this.#jobs.get(job.jobId);
    if (!fresh || fresh.stage !== 'waiting-admission' || fresh.cancelRequested) return;
    await this.#jobs.update(job.jobId, (draft) => {
      draft.stage = 'acquiring';
      draft.attempt += 1;
    });
    const outcome = await sendMessage(
      'page:acquire',
      {
        sessionId: job.target.sessionId,
        candidateId: job.target.candidateId,
        allowScreenshot: job.allowScreenshot,
        previewOnPage: false
      },
      { tabId: job.target.tabId, frameId: 0 }
    ).catch((cause) => ({
      ok: false as const,
      failure: {
        reason: 'failed' as const,
        candidateId: job.target.candidateId,
        code: 'STALE_SESSION',
        message: cause instanceof Error ? cause.message : 'Content Script acquisition channel is unavailable.'
      }
    }));
    if (!outcome.ok) {
      this.#acquisitionFailures.set(job.jobId, outcome.failure);
      await this.#jobs.update(job.jobId, (draft) => {
        draft.stage = 'failed';
        draft.lastErrorCode = outcome.failure.reason === 'failed' ? outcome.failure.code : outcome.failure.reason === 'permission-needed' ? 'PERMISSION_NEEDED' : 'CANDIDATE_NOT_READY';
      });
      return;
    }
    try {
      await this.#stageAcquired(job.jobId, outcome.image);
    } finally {
      if (outcome.image.acquisitionId) this.#acquisitions.release(outcome.image.acquisitionId);
    }
  }

  async #stageAcquired(jobId: string, acquired: AcquiredImage): Promise<void> {
    const job = await this.#jobs.get(jobId);
    if (!job) throw new AppError('JOB_NOT_FOUND', 'Job disappeared before source staging.');
    const resolved = this.#resolveAcquiredBlob(job.target.sessionId, job.target.candidateId, acquired);
    if (!resolved) throw new AppError('BINARY_NOT_FOUND', 'Acquisition payload expired before durable queue staging.');
    const validated = await validatePipelineSource(acquired, resolved.blob);
    await this.#jobs.update(jobId, (draft) => {
      draft.stage = 'staging-source';
      draft.sourceRaster = {
        pixelWidth: validated.pixelWidth,
        pixelHeight: validated.pixelHeight,
        ...(acquired.capture ? { capture: acquired.capture } : {})
      };
    });
    const source = await this.#binaries.stageOwned({
      blob: validated.blob,
      purpose: 'source',
      runtimeSessionId: job.runtimeSessionId,
      lease: { ownerType: 'job', ownerId: jobId, role: 'source', runtimeSessionId: job.runtimeSessionId }
    });
    await this.#jobs.update(jobId, (draft) => {
      draft.source = source;
      draft.stage = 'hashing';
    });
    await this.#hashJob(jobId);
  }

  async #hashJob(jobId: string): Promise<void> {
    await this.#hashLane.run(async () => {
      const job = await this.#jobs.get(jobId);
      if (!job || job.stage !== 'hashing' || !job.source || !job.sourceRaster) return;
      const memory = await this.#memory.reserve(job.source.byteLength);
      try {
        const blob = await this.#binaries.get(job.source.binaryId, { ownerType: 'job', ownerId: job.jobId, role: 'source' });
        const sourceSha256 = await sha256Blob(blob);
        const source = await this.#binaries.attachHash(job.source.binaryId, sourceSha256);
        const specFingerprint = await processingSpecFingerprint(job.processingSpec);
        const signature = await deriveWorkSignature({
          sourceSha256,
          processingSpec: job.processingSpec,
          engineProfileFingerprint: job.engineProfileFingerprint
        });
        const cacheKey = await deriveResultCacheKey({
          sourceSha256,
          processingSpecFingerprint: specFingerprint,
          engineProfileFingerprint: job.engineProfileFingerprint
        });
        await this.#jobs.update(job.jobId, (draft) => {
          draft.source = source;
          draft.sourceSha256 = sourceSha256;
          draft.processingSpecFingerprint = specFingerprint;
          draft.signature = signature;
          draft.cacheKey = cacheKey;
          draft.stage = 'waiting-work';
        });
      } finally {
        memory.release();
      }
    });
  }

  async #attachHashedJobs(): Promise<boolean> {
    const jobs = (await this.#jobs.listNonTerminal()).filter((job) => job.stage === 'waiting-work' && job.signature && job.cacheKey && job.source && job.sourceSha256 && job.processingSpecFingerprint && job.sourceRaster);
    if (jobs.length === 0) return false;
    jobs.sort(compareJobs);
    let progressed = false;
    for (const job of jobs) {
      const hit = await this.#cache.lookup({ cacheKey: job.cacheKey!, jobId: job.jobId, runtimeSessionId: job.runtimeSessionId });
      if (hit) {
        await this.#jobs.update(job.jobId, (draft) => {
          draft.cacheHit = true;
          draft.result = hit.result;
          draft.resultRaster = { pixelWidth: hit.width, pixelHeight: hit.height, ...(draft.sourceRaster?.capture ? { capture: draft.sourceRaster.capture } : {}) };
          draft.stage = 'delivering';
        });
        await this.#binaries.releaseLease({ binaryId: job.source!.binaryId, ownerType: 'job', ownerId: job.jobId, role: 'source' }).catch(() => undefined);
        progressed = true;
        continue;
      }

      const existing = await this.#works.findBySignature(job.signature!);
      if (existing) {
        await this.#jobs.update(job.jobId, (draft) => {
          draft.workId = existing.workId;
          draft.cacheHit = false;
          draft.stage = 'joined-work';
        });
        await this.#binaries.releaseLease({ binaryId: job.source!.binaryId, ownerType: 'job', ownerId: job.jobId, role: 'source' }).catch(() => undefined);
        progressed = true;
        continue;
      }

      // The work owner id is deterministic from the signature. Acquire its source lease
      // before publishing the WorkRecord so a worker death cannot expose runnable work
      // without durable bytes; retrying this step is idempotent.
      const proposedWorkId = workIdFromSignature(job.signature!);
      await this.#binaries.acquireLease({
        binaryId: job.source!.binaryId,
        ownerType: 'work',
        ownerId: proposedWorkId,
        role: 'source',
        runtimeSessionId: job.runtimeSessionId
      });
      const proposed: WorkRecord = {
        workId: proposedWorkId,
        runtimeSessionId: job.runtimeSessionId,
        jobSignature: job.signature!,
        sourceBinaryId: job.source!.binaryId,
        sourceSha256: job.sourceSha256!,
        sourceRaster: job.sourceRaster!,
        processingSpecFingerprint: job.processingSpecFingerprint!,
        processingSpec: structuredClone(job.processingSpec),
        engineProfileFingerprint: job.engineProfileFingerprint,
        stage: 'queued',
        suppressCachePromotion: false,
        attempt: 0,
        createdAt: Date.now(),
        updatedAt: Date.now()
      };
      let joined: Awaited<ReturnType<WorkStore['createOrGetBySignature']>>;
      try {
        joined = await this.#works.createOrGetBySignature(proposed);
      } catch (error) {
        await this.#binaries.releaseLease({ binaryId: job.source!.binaryId, ownerType: 'work', ownerId: proposedWorkId, role: 'source' }).catch(() => undefined);
        throw error;
      }
      if (!joined.created && joined.record.sourceBinaryId !== job.source!.binaryId) {
        // A canonical WorkRecord won a rare race; discard only our temporary lease.
        await this.#binaries.releaseLease({ binaryId: job.source!.binaryId, ownerType: 'work', ownerId: proposedWorkId, role: 'source' }).catch(() => undefined);
      }
      await this.#jobs.update(job.jobId, (draft) => {
        draft.workId = joined.record.workId;
        draft.cacheHit = false;
        draft.stage = joined.created ? 'waiting-work' : 'joined-work';
      });
      await this.#binaries.releaseLease({ binaryId: job.source!.binaryId, ownerType: 'job', ownerId: job.jobId, role: 'source' }).catch(() => undefined);
      progressed = true;
    }
    return progressed;
  }

  async #processOneWork(): Promise<boolean> {
    const now = Date.now();
    const works = (await this.#works.listRunnable(now)).sort((a, b) => a.createdAt - b.createdAt || a.workId.localeCompare(b.workId));
    const work = works.find((candidate) => candidate.stage !== 'ready' && candidate.stage !== 'failed' && candidate.stage !== 'cancelled');
    if (!work) return false;
    await this.#engineLane.run(async () => {
      let current = await this.#works.get(work.workId);
      if (!current || current.stage === 'ready' || current.stage === 'failed' || current.stage === 'cancelled') return;
      const source = await this.#binaries.findOwnedBinary('work', current.workId, 'source');
      if (!source) {
        await this.#works.update(current.workId, (draft) => {
          draft.stage = 'failed';
          draft.lastErrorCode = 'BINARY_NOT_FOUND';
        });
        return;
      }
      if (!current.processingSpec) {
        const donor = (await this.#jobs.list()).find((job) => job.workId === current!.workId || job.signature === current!.jobSignature);
        if (!donor) {
          await this.#works.update(current.workId, (draft) => { draft.stage = 'failed'; draft.lastErrorCode = 'PROCESSING_SPEC_INVALID'; });
          return;
        }
        current = await this.#works.update(current.workId, (draft) => { draft.processingSpec = structuredClone(donor.processingSpec); });
      }
      const memory = await this.#memory.reserve(source.byteLength);
      try {
        if (current.stage === 'validating-result' && current.resultBinaryId) {
          await this.#finalizeEngineResult(current.workId);
          return;
        }
        if (current.stage === 'fetching-result' && current.engineTicket) {
          await this.#downloadEngineResult(current, current.engineTicket);
          return;
        }
        if (current.stage === 'cancelling') {
          if (!current.engineTicket) {
            await this.#works.update(current.workId, (draft) => { draft.stage = 'cancelled'; delete draft.notBefore; });
            return;
          }
          await this.#gateway.cancelJob(current.engineTicket);
          const status = await this.#gateway.getJob(current.engineTicket);
          if (status.state === 'cancelled') {
            await this.#works.update(current.workId, (draft) => { draft.stage = 'cancelled'; draft.lastErrorCode = 'ENGINE_JOB_CANCELLED'; delete draft.notBefore; });
            await this.#gateway.releaseJob(current.engineTicket).catch(() => undefined);
          } else {
            await this.#works.update(current.workId, (draft) => { draft.stage = 'cancelling'; draft.notBefore = Date.now() + ENGINE_DURABLE_RECHECK_MS; });
          }
          return;
        }

        let ticket = current.engineTicket;
        if (!ticket) {
          await this.#works.update(current.workId, (draft) => {
            draft.stage = 'submitting';
            draft.attempt += 1;
            delete draft.notBefore;
          });
          const created = await this.#gateway.createJob({
            jobId: current.workId,
            idempotencyKey: current.jobSignature,
            sourceSha256: current.sourceSha256,
            sourceBytes: source.byteLength,
            sourceMime: source.mimeType,
            processingSpec: current.processingSpec!,
            expectedProfileFingerprint: current.engineProfileFingerprint
          });
          const durableTicket = created.engineTicket;
          ticket = durableTicket;
          // Persist the durable external ticket immediately. If the worker dies before this
          // write, the same idempotency key recovers the exact same ticket on resubmission.
          current = await this.#works.update(current.workId, (draft) => {
            draft.engineTicket = durableTicket;
            draft.stage = created.state === 'completed' || created.state === 'succeeded' ? 'fetching-result' : 'submitting';
          });
          if (created.state === 'completed' || created.state === 'succeeded') {
            await this.#downloadEngineResult(current, ticket);
            return;
          }
        }

        if (!ticket) throw new AppError('ENGINE_JOB_NOT_FOUND', 'Engine ticket was not persisted after submission.');
        let status = await this.#gateway.getJob(ticket);
        await this.#recordEngineStatus(current.workId, status);

        if (status.state === 'awaiting_source') {
          const sourceBlob = await this.#binaries.get(source.binaryId, { ownerType: 'work', ownerId: current.workId, role: 'source' });
          await this.#gateway.uploadSource({ ticket, blob: sourceBlob, sourceSha256: current.sourceSha256, sourceMime: source.mimeType });
          await this.#gateway.startJob(ticket, { profileId: current.processingSpec!.profileId, expectedProfileFingerprint: current.engineProfileFingerprint });
          status = await this.#gateway.getJob(ticket);
          await this.#recordEngineStatus(current.workId, status);
        } else if (status.state === 'interrupted') {
          // Engine startup converts in-flight work to interrupted. The source spool survives,
          // so POST /start safely requeues the same durable ticket/idempotency record.
          await this.#gateway.startJob(ticket, { profileId: current.processingSpec!.profileId, expectedProfileFingerprint: current.engineProfileFingerprint });
          status = await this.#gateway.getJob(ticket);
          await this.#recordEngineStatus(current.workId, status);
        }

        const deadline = Date.now() + ENGINE_POLL_GRACE_MS;
        while (true) {
          if (status.state === 'succeeded') {
            await this.#works.update(current.workId, (draft) => { draft.stage = 'fetching-result'; delete draft.notBefore; });
            await this.#downloadEngineResult((await this.#works.get(current.workId))!, ticket);
            return;
          }
          if (status.state === 'failed') {
            if (status.error?.code === 'profile_changed') {
              throw new AppError('ENGINE_PROFILE_CHANGED', status.error.message ?? 'Local Engine profile changed while work was durable.');
            }
            throw new AppError('ENGINE_REQUEST_FAILED', status.error?.message ?? 'Local Engine job failed.', {
              retryable: status.error?.retryable ?? false,
              ...(status.error?.code ? { details: { engineCode: status.error.code } } : {})
            });
          }
          if (status.state === 'cancelled') {
            await this.#works.update(current.workId, (draft) => { draft.stage = 'cancelled'; draft.lastErrorCode = 'ENGINE_JOB_CANCELLED'; delete draft.notBefore; });
            await this.#gateway.releaseJob(ticket).catch(() => undefined);
            return;
          }
          if (status.state === 'interrupted') {
            await this.#gateway.startJob(ticket, { profileId: current.processingSpec!.profileId, expectedProfileFingerprint: current.engineProfileFingerprint });
          }
          if (Date.now() >= deadline) break;
          await delay(ENGINE_POLL_INTERVAL_MS);
          status = await this.#gateway.getJob(ticket);
          await this.#recordEngineStatus(current.workId, status);
        }
        await this.#works.update(current.workId, (draft) => {
          draft.stage = status.state === 'cancel_requested' ? 'cancelling' : 'processing';
          draft.notBefore = Date.now() + ENGINE_DURABLE_RECHECK_MS;
          delete draft.lastErrorCode;
        });
      } catch (error) {
        let serialized = serializeError(error);
        if (serialized.code === 'ENGINE_PROFILE_CHANGED') {
          try {
            await this.#migrateWorkToCurrentProfile(current.workId);
            return;
          } catch (migrationError) {
            serialized = serializeError(migrationError);
          }
        }
        const latest = await this.#works.get(current.workId);
        if (serialized.retryable && latest?.engineTicket) {
          await this.#works.update(current.workId, (draft) => {
            draft.stage = draft.stage === 'cancelling' ? 'cancelling' : 'processing';
            draft.lastErrorCode = serialized.code;
            draft.notBefore = Date.now() + ENGINE_DURABLE_RECHECK_MS;
          });
        } else {
          await this.#works.update(current.workId, (draft) => {
            draft.stage = 'failed';
            draft.lastErrorCode = serialized.code;
            delete draft.notBefore;
          });
        }
      } finally {
        memory.release();
      }
    });
    return true;
  }

  async #recordEngineStatus(workId: string, status: EngineJobStatus): Promise<void> {
    await this.#works.update(workId, (draft) => {
      if (status.stage) draft.engineStage = status.stage;
      else delete draft.engineStage;
      if (status.progress && status.progress.total > 0 && status.progress.completed >= 0 && status.progress.completed <= status.progress.total) {
        draft.engineProgress = { completed: status.progress.completed, total: status.progress.total };
      } else {
        delete draft.engineProgress;
      }
    });
  }

  async #migrateWorkToCurrentProfile(workId: string): Promise<void> {
    const work = await this.#works.get(workId);
    if (!work) throw new AppError('JOB_NOT_FOUND', 'Profile migration could not find the durable WorkRecord.');
    const source = await this.#binaries.findOwnedBinary('work', work.workId, 'source');
    if (!source) throw new AppError('BINARY_NOT_FOUND', 'Profile migration requires the durable work source.');
    const processingSpec = work.processingSpec ?? (await this.#jobs.list()).find((job) => job.workId === work.workId || job.signature === work.jobSignature)?.processingSpec;
    if (!processingSpec) throw new AppError('PROCESSING_SPEC_INVALID', 'Profile migration could not recover ProcessingSpec.');

    const currentProfileFingerprint = await this.#gateway.refreshProfileFingerprint(processingSpec.profileId);
    if (currentProfileFingerprint === work.engineProfileFingerprint) {
      throw new AppError('ENGINE_PROFILE_CHANGED', 'Engine reported a profile change but capabilities still expose the previous fingerprint.');
    }

    const newSignature = await deriveWorkSignature({
      sourceSha256: work.sourceSha256,
      processingSpec,
      engineProfileFingerprint: currentProfileFingerprint
    });
    const newCacheKey = await deriveResultCacheKey({
      sourceSha256: work.sourceSha256,
      processingSpecFingerprint: work.processingSpecFingerprint,
      engineProfileFingerprint: currentProfileFingerprint
    });
    const consumers = (await this.#jobs.listNonTerminal()).filter((job) => job.workId === work.workId || job.signature === work.jobSignature);

    // Reattach the already-hashed source to each Job before releasing the obsolete Work owner.
    // The normal waiting-work path then performs cache lookup and final Work dedupe under the
    // new profile-derived identity instead of silently reusing the stale signature.
    for (const job of consumers) {
      await this.#binaries.acquireLease({
        binaryId: source.binaryId,
        ownerType: 'job',
        ownerId: job.jobId,
        role: 'source',
        runtimeSessionId: job.runtimeSessionId
      });
      await this.#jobs.update(job.jobId, (draft) => {
        draft.source = source;
        draft.engineProfileFingerprint = currentProfileFingerprint;
        draft.signature = newSignature;
        draft.cacheKey = newCacheKey;
        draft.cacheHit = false;
        delete draft.workId;
        delete draft.lastErrorCode;
        delete draft.notBefore;
        draft.stage = 'waiting-work';
      });
    }

    if (work.engineTicket) await this.#gateway.releaseJob(work.engineTicket).catch(() => undefined);
    await this.#binaries.releaseOwner('work', work.workId).catch(() => undefined);
    await this.#works.remove(work.workId);
  }

  async #downloadEngineResult(work: WorkRecord, ticket: string): Promise<void> {
    const payload = await this.#gateway.fetchResult({
      ticket,
      expectedProfileFingerprint: work.engineProfileFingerprint,
      expectedWidth: work.sourceRaster.pixelWidth,
      expectedHeight: work.sourceRaster.pixelHeight
    });
    const validated = await validatePipelineResult({
      blob: payload.blob,
      expectedWidth: work.sourceRaster.pixelWidth,
      expectedHeight: work.sourceRaster.pixelHeight,
      encoderSemantics: payload.encoderSemantics
    });
    const result = await this.#resultLane.run(async () => await this.#binaries.stageOwned({
      blob: validated.blob,
      purpose: 'result',
      runtimeSessionId: work.runtimeSessionId,
      lease: { ownerType: 'work', ownerId: work.workId, role: 'result', runtimeSessionId: work.runtimeSessionId }
    }));
    await this.#works.update(work.workId, (draft) => {
      draft.resultBinaryId = result.binaryId;
      draft.resultEncoderSemantics = payload.encoderSemantics;
      draft.resultRaster = { pixelWidth: validated.pixelWidth, pixelHeight: validated.pixelHeight, ...(draft.sourceRaster.capture ? { capture: draft.sourceRaster.capture } : {}) };
      draft.stage = 'validating-result';
      delete draft.notBefore;
    });
    await this.#finalizeEngineResult(work.workId);
  }

  async #finalizeEngineResult(workId: string): Promise<void> {
    const work = await this.#works.get(workId);
    if (!work || !work.resultBinaryId) throw new AppError('BINARY_NOT_FOUND', 'Engine result disappeared before validation.');
    const result = await this.#binaries.findOwnedBinary('work', work.workId, 'result');
    if (!result || result.binaryId !== work.resultBinaryId) throw new AppError('BINARY_NOT_FOUND', 'Engine result lease is missing.');
    const staged = await this.#binaries.get(result.binaryId, { ownerType: 'work', ownerId: work.workId, role: 'result' });
    const semantics = work.resultEncoderSemantics ?? 'engine-exact-lossless-v1';
    const validated = await validatePipelineResult({
      blob: staged,
      expectedWidth: work.sourceRaster.pixelWidth,
      expectedHeight: work.sourceRaster.pixelHeight,
      encoderSemantics: semantics
    });
    const ready = await this.#works.update(work.workId, (draft) => {
      draft.resultEncoderSemantics = semantics;
      draft.resultRaster = { pixelWidth: validated.pixelWidth, pixelHeight: validated.pixelHeight, ...(draft.sourceRaster.capture ? { capture: draft.sourceRaster.capture } : {}) };
      draft.stage = 'ready';
      delete draft.notBefore;
      delete draft.lastErrorCode;
    });
    if (!ready.suppressCachePromotion && ready.resultBinaryId && ready.resultRaster) {
      const cacheKey = await deriveResultCacheKey({
        sourceSha256: ready.sourceSha256,
        processingSpecFingerprint: ready.processingSpecFingerprint,
        engineProfileFingerprint: ready.engineProfileFingerprint
      });
      await this.#cache.promote({
        cacheKey,
        sourceSha256: ready.sourceSha256,
        processingSpecFingerprint: ready.processingSpecFingerprint,
        engineProfileFingerprint: ready.engineProfileFingerprint,
        resultBinaryId: ready.resultBinaryId,
        byteLength: result.byteLength,
        mimeType: result.mimeType,
        width: ready.resultRaster.pixelWidth,
        height: ready.resultRaster.pixelHeight
      }).catch(() => 'skipped-quota');
    }
    await this.#binaries.releaseLease({ binaryId: ready.sourceBinaryId, ownerType: 'work', ownerId: ready.workId, role: 'source' }).catch(() => undefined);
    if (ready.engineTicket) await this.#gateway.releaseJob(ready.engineTicket).catch(() => undefined);
  }

  async #hydrateJobsFromReadyWork(): Promise<boolean> {
    const jobs = (await this.#jobs.listNonTerminal()).filter((job) => (job.stage === 'waiting-work' || job.stage === 'joined-work') && job.workId);
    if (jobs.length === 0) return false;
    let progressed = false;
    const allowedJobs: JobRecord[] = [];
    const byWork = new Map<string, JobRecord[]>();
    for (const job of jobs) {
      const bucket = byWork.get(job.workId!) ?? [];
      bucket.push(job);
      byWork.set(job.workId!, bucket);
    }
    for (const bucket of byWork.values()) {
      bucket.sort(compareJobs);
      allowedJobs.push(...bucket.slice(0, MAX_WORK_CONSUMERS));
      for (const overflow of bucket.slice(MAX_WORK_CONSUMERS)) {
        await this.#failJob(overflow.jobId, new AppError('JOB_STATE_CONFLICT', 'Work consumer fan-out exceeded the defensive limit.'));
        progressed = true;
      }
    }
    allowedJobs.sort(compareJobs);
    for (const job of allowedJobs) {
      const work = await this.#works.get(job.workId!);
      if (!work) {
        await this.#failJob(job.jobId, new AppError('JOB_NOT_FOUND', 'Joined work disappeared before delivery.'));
        progressed = true;
        continue;
      }
      if (work.stage === 'failed' || work.stage === 'cancelled') {
        await this.#failJob(job.jobId, new AppError(work.stage === 'cancelled' ? 'ENGINE_JOB_CANCELLED' : 'ENGINE_REQUEST_FAILED', work.lastErrorCode ?? 'Shared engine work failed.'));
        progressed = true;
        continue;
      }
      if (work.stage !== 'ready' || !work.resultBinaryId || !work.resultRaster || !work.resultEncoderSemantics) continue;
      const result = await this.#binaries.findOwnedBinary('work', work.workId, 'result');
      if (!result) {
        await this.#failJob(job.jobId, new AppError('BINARY_NOT_FOUND', 'Ready work lost its result binary.'));
        progressed = true;
        continue;
      }
      await this.#binaries.acquireLease({
        binaryId: result.binaryId,
        ownerType: 'job',
        ownerId: job.jobId,
        role: 'delivery',
        runtimeSessionId: job.runtimeSessionId
      });
      await this.#jobs.update(job.jobId, (draft) => {
        draft.result = result;
        draft.resultRaster = work.resultRaster!;
        draft.resultEncoderSemantics = work.resultEncoderSemantics!;
        draft.stage = 'delivering';
      });
      progressed = true;
    }
    return progressed;
  }

  async #deliverReadyJobs(): Promise<boolean> {
    const jobs = (await this.#jobs.listNonTerminal()).filter((job) => job.stage === 'delivering' && job.result && job.resultRaster).sort(compareJobs);
    if (jobs.length === 0) return false;
    const batch = jobs.slice(0, this.#deliveryLane.capacity);
    await Promise.all(batch.map((job) => this.#deliveryLane.run(async () => {
      try {
        await this.#deliver(job.jobId);
      } catch (error) {
        await this.#failJob(job.jobId, error);
      }
    })));
    return true;
  }

  async #deliver(jobId: string): Promise<PipelineStartResult> {
    const job = await this.#jobs.get(jobId);
    if (!job || !job.result || !job.resultRaster) throw new AppError('JOB_NOT_FOUND', 'Delivering job is missing result metadata.');
    const current = await this.#sessions.get(job.target.tabId);
    if (!isJobFreshForDelivery(current, job)) {
      const stale = await this.#jobs.update(job.jobId, (draft) => {
        draft.staleForDelivery = true;
        draft.stage = 'stale';
        draft.cancellationKind = 'navigation-stale';
        draft.lastErrorCode = 'STALE_TARGET';
      });
      await this.#binaries.releaseOwner('job', job.jobId).catch(() => undefined);
      return resultFromJob(stale);
    }
    await this.#binaries.acquireLease({
      binaryId: job.result.binaryId,
      ownerType: 'job',
      ownerId: job.jobId,
      role: 'delivery',
      runtimeSessionId: job.runtimeSessionId
    });
    const memory = await this.#memory.reserve(job.result.byteLength);
    let ack;
    try {
      const blob = await this.#binaries.get(job.result.binaryId, { ownerType: 'job', ownerId: job.jobId, role: 'delivery' });
      const uiSettings = await this.#uiSettings.get();
      ack = await sendMessage(
        'page:deliver-result',
        {
          target: job.target,
          presentation: {
            autoShow: uiSettings.autoShowTranslatedResult,
            showCompactControls: uiSettings.showCompactControls,
            locale: effectiveLocale(uiSettings.uiLocale)
          },
          result: {
            mimeType: job.result.mimeType as 'image/png' | 'image/webp',
            byteLength: job.result.byteLength,
            pixelWidth: job.resultRaster.pixelWidth,
            pixelHeight: job.resultRaster.pixelHeight,
            blob,
            ...(job.resultRaster.capture ? { capture: job.resultRaster.capture } : {})
          }
        },
        { tabId: job.target.tabId, frameId: 0 }
      );
    } catch (cause) {
      throw new AppError('DELIVERY_FAILED', 'Content Script did not acknowledge translated raster delivery.', { cause, retryable: true });
    } finally {
      memory.release();
    }
    if (ack.status === 'applied') {
      const applied = await this.#jobs.update(job.jobId, (draft) => {
        draft.stage = 'applied';
      });
      await this.#binaries.releaseOwner('job', job.jobId).catch(() => undefined);
      return resultFromJob(applied);
    }
    if (ack.status === 'stored') {
      const stored = await this.#jobs.update(job.jobId, (draft) => {
        draft.stage = 'ready-result';
      });
      await this.#binaries.releaseOwner('job', job.jobId).catch(() => undefined);
      return resultFromJob(stored);
    }
    if (ack.status === 'stale') {
      const stale = await this.#jobs.update(job.jobId, (draft) => {
        draft.staleForDelivery = true;
        draft.stage = 'stale';
        draft.cancellationKind = 'navigation-stale';
        draft.lastErrorCode = ack.code;
      });
      await this.#binaries.releaseOwner('job', job.jobId).catch(() => undefined);
      return resultFromJob(stale);
    }
    throw new AppError('DELIVERY_FAILED', ack.message);
  }

  async #cleanupCompletedWorks(): Promise<void> {
    const jobs = await this.#jobs.list();
    const activeByWork = new Map<string, number>();
    for (const job of jobs) {
      if (job.workId && !isTerminalJobStage(job.stage)) activeByWork.set(job.workId, (activeByWork.get(job.workId) ?? 0) + 1);
    }
    for (const work of await this.#works.list()) {
      if ((activeByWork.get(work.workId) ?? 0) > 0) continue;
      if (work.stage === 'submitting' || work.stage === 'processing' || work.stage === 'fetching-result' || work.stage === 'validating-result' || work.stage === 'cancelling') continue;
      await this.#binaries.releaseOwner('work', work.workId).catch(() => undefined);
      await this.#works.remove(work.workId);
    }
  }

  async #reconcileAlarm(): Promise<void> {
    const times = [
      ...(await this.#jobs.listNonTerminal()).map((job) => job.notBefore).filter((value): value is number => typeof value === 'number'),
      ...(await this.#works.list()).map((work) => work.notBefore).filter((value): value is number => typeof value === 'number')
    ];
    await this.#retryWake.reconcile(times);
  }

  async #createJob(input: {
    session: StoredPageSession;
    candidateId: string;
    sourceRevision: number;
    allowScreenshot: boolean;
    explicit: boolean;
    processingSpec?: ProcessingSpec;
  }): Promise<JobRecord> {
    const runtime = await this.#runtimeSessions.getOrCreate();
    const processingSpec = structuredClone(input.processingSpec ?? DEFAULT_PROCESSING_SPEC);
    validateProcessingSpec(processingSpec);
    const engineProfileFingerprint = await this.#gateway.getProfileFingerprint(processingSpec.profileId);
    const candidate = input.session.candidates[input.candidateId];
    if (!candidate || !input.session.documentId) throw new AppError('CANDIDATE_NOT_FOUND', 'Candidate disappeared before job creation.');
    const now = Date.now();
    const job: JobRecord = {
      jobId: newJobId(),
      runtimeSessionId: runtime.runtimeSessionId,
      target: {
        sessionId: input.session.sessionId,
        tabId: input.session.tabId,
        documentId: input.session.documentId,
        candidateId: input.candidateId,
        sourceRevision: input.sourceRevision
      },
      processingSpec,
      engineProfileFingerprint,
      allowScreenshot: input.allowScreenshot,
      schedulingHint: buildSchedulingHint({
        explicit: input.explicit,
        visibility: candidate.visibility ?? 'far',
        readingOrder: candidate.orderHint ?? Number.MAX_SAFE_INTEGER,
        ...(candidate.estimatedSourceBytes !== undefined ? { estimatedSourceBytes: candidate.estimatedSourceBytes } : {})
      }),
      stage: 'waiting-admission',
      attempt: 0,
      cancelRequested: false,
      staleForDelivery: false,
      createdAt: now,
      updatedAt: now
    };
    await this.#jobs.create(job);
    return job;
  }

  #resolveAcquiredBlob(sessionId: string, candidateId: string, acquired: AcquiredImage): { blob: Blob } | null {
    if (acquired.blob) return { blob: acquired.blob };
    if (!acquired.acquisitionId) return null;
    const stored = this.#acquisitions.getOwned(acquired.acquisitionId, sessionId, candidateId);
    return stored ? { blob: stored.blob } : null;
  }

  async #failJob(jobId: string, error: unknown): Promise<PipelineStartResult> {
    const serialized = serializeError(error);
    let job = await this.#jobs.get(jobId);
    if (!job) return failureResult(jobId, serialized.code);
    if (!isTerminalJobStage(job.stage)) {
      job = await this.#jobs.update(jobId, (draft) => {
        draft.stage = 'failed';
        draft.lastErrorCode = serialized.code;
      });
    }
    await this.#binaries.releaseOwner('job', jobId).catch(() => undefined);
    return resultFromJob(job);
  }
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function resultFromJob(job: JobRecord): PipelineStartResult {
  return {
    jobId: job.jobId,
    stage: job.stage,
    ...(job.signature ? { signature: job.signature } : {}),
    ...(job.workId ? { workId: job.workId } : {}),
    ...(job.cacheHit !== undefined ? { cacheHit: job.cacheHit } : {}),
    applied: job.stage === 'applied',
    stale: job.stage === 'stale',
    ...(job.lastErrorCode ? { errorCode: job.lastErrorCode } : {})
  };
}

function failureResult(jobId: string, errorCode: string): PipelineStartResult {
  return {
    jobId,
    stage: 'failed',
    applied: false,
    stale: errorCode === 'STALE_TARGET' || errorCode === 'STALE_SESSION' || errorCode === 'STALE_DOCUMENT',
    errorCode
  };
}

function acquisitionFailure(candidateId: string, code: string, message: string): PageTranslateOutcome {
  return { ok: false, failure: { reason: 'failed', candidateId, code, message } };
}
