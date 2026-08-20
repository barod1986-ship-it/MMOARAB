import { sendMessage, type SessionEnvelope } from '../messaging/protocol.js';
import { CandidateRegistry } from './detector.js';
import { PageObservers } from './observers.js';
import { genericAdapter } from './adapters/generic.js';
import { PresentationManager } from './presentation/index.js';
import { AcquisitionCoordinator } from './acquisition/coordinator.js';
import type { AcquisitionOutcome, PageSnapshot } from './types.js';
import type { DeliverResultMessage, DeliveryAck, PageTranslateOutcome } from '../pipeline/types.js';

export class PageSessionRuntime {
  readonly envelope: SessionEnvelope;
  readonly #registry: CandidateRegistry;
  readonly #presentation: PresentationManager;
  readonly #acquisition: AcquisitionCoordinator;
  #observers: PageObservers | null = null;
  #lastSnapshot: PageSnapshot;
  #publishTimer: number | null = null;
  #disposed = false;
  readonly #onSpaNavigation: (pageUrl: string) => void;

  constructor(envelope: SessionEnvelope, onSpaNavigation: (pageUrl: string) => void) {
    this.envelope = envelope;
    this.#onSpaNavigation = onSpaNavigation;
    this.#registry = new CandidateRegistry(envelope.sessionId, genericAdapter);
    this.#presentation = new PresentationManager();
    this.#acquisition = new AcquisitionCoordinator({
      sessionId: envelope.sessionId,
      mainFrameOrigin: envelope.mainFrameOrigin,
      registry: this.#registry,
      presentation: this.#presentation
    });
    this.#lastSnapshot = {
      sessionId: envelope.sessionId,
      pageUrl: location.href,
      candidates: [],
      updatedAt: Date.now()
    };
  }

  start(): PageSnapshot {
    const root = genericAdapter.findReaderRoot(document) ?? document.documentElement;
    this.#observers = new PageObservers({
      registry: this.#registry,
      root,
      onSnapshot: (snapshot) => {
        this.#lastSnapshot = snapshot;
        this.#syncPresentationTargets(snapshot);
        this.#schedulePublish();
      },
      onUrlChanged: (nextUrl) => this.#onSpaNavigation(nextUrl)
    });
    this.#lastSnapshot = this.#observers.start();
    return this.#lastSnapshot;
  }

  snapshot(): PageSnapshot {
    return this.#lastSnapshot;
  }

  async acquire(candidateId: string, options: { allowScreenshot: boolean; previewOnPage: boolean }): Promise<AcquisitionOutcome> {
    if (this.#disposed) {
      return {
        ok: false,
        failure: { reason: 'failed', candidateId, code: 'STALE_SESSION', message: 'Page session has already been disposed.' }
      };
    }
    const result = await this.#acquisition.acquire(candidateId, options);
    this.#lastSnapshot = this.#registry.snapshot();
    this.#schedulePublish();
    return result;
  }


  async translate(candidateId: string, allowScreenshot: boolean): Promise<PageTranslateOutcome> {
    if (this.#disposed) {
      return {
        ok: false,
        failure: { reason: 'failed', candidateId, code: 'STALE_SESSION', message: 'Page session has already been disposed.' }
      };
    }
    const before = this.#registry.get(candidateId);
    if (!before) {
      return {
        ok: false,
        failure: { reason: 'failed', candidateId, code: 'CANDIDATE_NOT_FOUND', message: 'Candidate is not part of the current PageSession.' }
      };
    }
    const sourceRevision = before.sourceRevision;
    const acquired = await this.acquire(candidateId, { allowScreenshot, previewOnPage: false });
    if (!acquired.ok) return acquired;
    const current = this.#registry.get(candidateId);
    if (!current || current.sourceRevision !== sourceRevision || current.state === 'stale') {
      return {
        ok: false,
        failure: { reason: 'failed', candidateId, code: 'STALE_SESSION', message: 'Candidate changed before pipeline intake.' }
      };
    }
    const result = await sendMessage('pipeline:intake', {
      sessionId: this.envelope.sessionId,
      candidateId,
      sourceRevision,
      acquired: acquired.image
    });
    return { ok: true, result };
  }

  async deliverResult(message: DeliverResultMessage): Promise<DeliveryAck> {
    if (this.#disposed || message.target.sessionId !== this.envelope.sessionId) {
      return { status: 'stale', code: 'STALE_SESSION' };
    }
    const candidate = this.#registry.get(message.target.candidateId);
    const target = this.#registry.getElement(message.target.candidateId);
    if (!candidate || !target || candidate.state === 'stale' || candidate.sourceRevision !== message.target.sourceRevision) {
      return { status: 'stale', code: 'STALE_TARGET' };
    }
    if (message.result.blob.size !== message.result.byteLength || message.result.blob.type !== message.result.mimeType) {
      return { status: 'failed', code: 'PRESENTATION_FAILED', message: 'Delivered result envelope does not match Blob metadata.' };
    }
    try {
      const presentationStatus = await this.#presentation.storeResult(
        message.target.candidateId,
        target,
        message.result.blob,
        message.result.capture,
        message.presentation
      );
      const after = this.#registry.get(message.target.candidateId);
      if (this.#disposed || !after || after.sourceRevision !== message.target.sourceRevision || after.state === 'stale') {
        this.#presentation.showOriginal(message.target.candidateId);
        return { status: 'stale', code: 'STALE_TARGET' };
      }
      this.#registry.updateState(message.target.candidateId, 'translated');
      this.#lastSnapshot = this.#registry.snapshot();
      this.#schedulePublish();
      return { status: presentationStatus };
    } catch (error) {
      return {
        status: 'failed',
        code: 'PRESENTATION_FAILED',
        message: error instanceof Error ? error.message : 'Translated raster failed to load.'
      };
    }
  }

  showOriginal(candidateId: string): boolean {
    const restored = this.#acquisition.showOriginal(candidateId);
    this.#lastSnapshot = this.#registry.snapshot();
    this.#schedulePublish();
    return restored;
  }

  restoreAll(): void {
    this.#acquisition.restoreAll();
    this.#lastSnapshot = this.#registry.snapshot();
    this.#schedulePublish();
  }

  dispose(): void {
    if (this.#disposed) return;
    this.#disposed = true;
    this.#observers?.dispose();
    this.#observers = null;
    if (this.#publishTimer !== null) window.clearTimeout(this.#publishTimer);
    this.#acquisition.dispose();
    this.#registry.clear();
  }


  #syncPresentationTargets(snapshot: PageSnapshot): void {
    for (const candidate of snapshot.candidates) {
      const target = this.#registry.getElement(candidate.candidateId);
      if (!target) continue;
      void this.#presentation.syncTarget(candidate.candidateId, target).then((result) => {
        if (this.#disposed) return;
        if (result === 'reattached' || result === 'same' || result === 'stored') {
          this.#registry.updateState(candidate.candidateId, 'translated');
        } else if (result === 'failed') {
          this.#registry.updateState(candidate.candidateId, 'ready');
        } else {
          return;
        }
        this.#lastSnapshot = this.#registry.snapshot();
        this.#schedulePublish();
      });
    }
  }

  #schedulePublish(): void {
    if (this.#disposed || this.#publishTimer !== null) return;
    this.#publishTimer = window.setTimeout(() => {
      this.#publishTimer = null;
      const snapshot = this.#lastSnapshot;
      void sendMessage('page:snapshot', { sessionId: this.envelope.sessionId, snapshot }).catch(() => {
        // Service worker may have been terminated/restarted; the next reconciliation will republish.
      });
    }, 250);
  }
}
