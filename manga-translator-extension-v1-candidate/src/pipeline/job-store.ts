import { browser } from 'wxt/browser';
import { AppError } from '../core/errors.js';
import type { JobRecord, PipelineStage } from './types.js';

const STORAGE_KEY = 'phase3.jobs';
const TERMINAL_STAGES = new Set<PipelineStage>(['ready-result', 'applied', 'failed', 'cancelled', 'stale']);

type JobMap = Record<string, JobRecord>;

export class JobStore {
  #writeTail: Promise<void> = Promise.resolve();

  async create(record: JobRecord): Promise<void> {
    await this.#mutate((all) => {
      if (all[record.jobId]) throw new AppError('JOB_STATE_CONFLICT', 'Job id already exists.');
      all[record.jobId] = structuredClone(record);
    });
  }

  async get(jobId: string): Promise<JobRecord | null> {
    await this.#writeTail;
    return (await this.#readAll())[jobId] ?? null;
  }

  async list(): Promise<JobRecord[]> {
    await this.#writeTail;
    return Object.values(await this.#readAll());
  }

  async listNonTerminal(): Promise<JobRecord[]> {
    return (await this.list()).filter((job) => !TERMINAL_STAGES.has(job.stage));
  }

  async update(jobId: string, mutator: (job: JobRecord) => void): Promise<JobRecord> {
    let result: JobRecord | null = null;
    await this.#mutate((all) => {
      const current = all[jobId];
      if (!current) throw new AppError('JOB_NOT_FOUND', `Job ${jobId} does not exist.`);
      mutator(current);
      current.updatedAt = Date.now();
      if (TERMINAL_STAGES.has(current.stage) && current.terminalAt === undefined) current.terminalAt = current.updatedAt;
      result = structuredClone(current);
    });
    if (!result) throw new AppError('JOB_NOT_FOUND', `Job ${jobId} does not exist.`);
    return result;
  }

  async remove(jobId: string): Promise<void> {
    await this.#mutate((all) => {
      delete all[jobId];
    });
  }

  async removeTerminalOlderThan(cutoff: number): Promise<number> {
    let removed = 0;
    await this.#mutate((all) => {
      for (const [jobId, job] of Object.entries(all)) {
        if (TERMINAL_STAGES.has(job.stage) && (job.terminalAt ?? job.updatedAt) < cutoff) {
          delete all[jobId];
          removed += 1;
        }
      }
    });
    return removed;
  }

  async #readAll(): Promise<JobMap> {
    const value = (await browser.storage.session.get(STORAGE_KEY))[STORAGE_KEY];
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return {};
    const result: JobMap = {};
    for (const [key, candidate] of Object.entries(value as Record<string, unknown>)) {
      if (isJobRecord(candidate)) result[key] = candidate;
    }
    return result;
  }

  async #writeAll(value: JobMap): Promise<void> {
    await browser.storage.session.set({ [STORAGE_KEY]: value });
  }

  async #mutate(mutator: (all: JobMap) => void): Promise<void> {
    const operation = this.#writeTail.then(async () => {
      const all = await this.#readAll();
      mutator(all);
      await this.#writeAll(all);
    });
    this.#writeTail = operation.catch(() => undefined);
    await operation;
  }
}

export function isTerminalJobStage(stage: PipelineStage): boolean {
  return TERMINAL_STAGES.has(stage);
}

function isJobRecord(value: unknown): value is JobRecord {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const job = value as Partial<JobRecord>;
  return (
    typeof job.jobId === 'string' &&
    typeof job.runtimeSessionId === 'string' &&
    typeof job.stage === 'string' &&
    typeof job.engineProfileFingerprint === 'string' &&
    typeof job.attempt === 'number' &&
    typeof job.allowScreenshot === 'boolean' &&
    typeof job.cancelRequested === 'boolean' &&
    typeof job.staleForDelivery === 'boolean' &&
    typeof job.createdAt === 'number' &&
    typeof job.updatedAt === 'number' &&
    typeof job.target === 'object' && job.target !== null &&
    typeof job.processingSpec === 'object' && job.processingSpec !== null &&
    typeof job.schedulingHint === 'object' && job.schedulingHint !== null
  );
}
