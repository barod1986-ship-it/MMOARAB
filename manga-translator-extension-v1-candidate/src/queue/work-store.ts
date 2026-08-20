import { browser } from 'wxt/browser';
import { AppError } from '../core/errors.js';
import type { WorkRecord, WorkStage } from '../pipeline/types.js';

const STORAGE_KEY = 'phase3.works';
const TERMINAL = new Set<WorkStage>(['failed', 'cancelled']);

type WorkMap = Record<string, WorkRecord>;

export class WorkStore {
  #writeTail: Promise<void> = Promise.resolve();

  async create(record: WorkRecord): Promise<void> {
    await this.#mutate((all) => {
      if (all[record.workId]) throw new AppError('JOB_STATE_CONFLICT', 'Work id already exists.');
      all[record.workId] = structuredClone(record);
    });
  }

  async createOrGetBySignature(record: WorkRecord): Promise<{ record: WorkRecord; created: boolean }> {
    let result: { record: WorkRecord; created: boolean } | null = null;
    await this.#mutate((all) => {
      const existing = Object.values(all)
        .filter((work) => work.jobSignature === record.jobSignature && !TERMINAL.has(work.stage))
        .sort((a, b) => a.createdAt - b.createdAt || a.workId.localeCompare(b.workId))[0];
      if (existing) {
        result = { record: structuredClone(existing), created: false };
        return;
      }
      all[record.workId] = structuredClone(record);
      result = { record: structuredClone(record), created: true };
    });
    if (!result) throw new AppError('JOB_STATE_CONFLICT', 'Unable to create or join work.');
    return result;
  }

  async get(workId: string): Promise<WorkRecord | null> {
    await this.#writeTail;
    return (await this.#readAll())[workId] ?? null;
  }

  async list(): Promise<WorkRecord[]> {
    await this.#writeTail;
    return Object.values(await this.#readAll());
  }

  async listRunnable(now = Date.now()): Promise<WorkRecord[]> {
    return (await this.list()).filter((work) => !TERMINAL.has(work.stage) && work.stage !== 'ready' && (work.notBefore ?? 0) <= now);
  }

  async findBySignature(signature: string): Promise<WorkRecord | null> {
    const matches = (await this.list())
      .filter((work) => work.jobSignature === signature && !TERMINAL.has(work.stage))
      .sort((a, b) => a.createdAt - b.createdAt || a.workId.localeCompare(b.workId));
    return matches[0] ?? null;
  }

  async update(workId: string, mutator: (work: WorkRecord) => void): Promise<WorkRecord> {
    let result: WorkRecord | null = null;
    await this.#mutate((all) => {
      const current = all[workId];
      if (!current) throw new AppError('JOB_NOT_FOUND', `Work ${workId} does not exist.`);
      mutator(current);
      current.updatedAt = Date.now();
      result = structuredClone(current);
    });
    if (!result) throw new AppError('JOB_NOT_FOUND', `Work ${workId} does not exist.`);
    return result;
  }

  async remove(workId: string): Promise<void> {
    await this.#mutate((all) => {
      delete all[workId];
    });
  }

  async reconcileDuplicateSignatures(): Promise<Array<{ duplicateWorkId: string; canonicalWorkId: string }>> {
    const merged: Array<{ duplicateWorkId: string; canonicalWorkId: string }> = [];
    await this.#mutate((all) => {
      const bySignature = new Map<string, WorkRecord[]>();
      for (const work of Object.values(all)) {
        if (TERMINAL.has(work.stage)) continue;
        const group = bySignature.get(work.jobSignature) ?? [];
        group.push(work);
        bySignature.set(work.jobSignature, group);
      }
      for (const group of bySignature.values()) {
        if (group.length <= 1) continue;
        group.sort((a, b) => {
          const aStarted = a.engineTicket || a.stage === 'processing' || a.stage === 'ready' ? 0 : 1;
          const bStarted = b.engineTicket || b.stage === 'processing' || b.stage === 'ready' ? 0 : 1;
          return aStarted - bStarted || a.createdAt - b.createdAt || a.workId.localeCompare(b.workId);
        });
        const canonical = group[0]!;
        for (const duplicate of group.slice(1)) {
          if (duplicate.engineTicket || duplicate.stage === 'processing' || duplicate.stage === 'ready') continue;
          delete all[duplicate.workId];
          merged.push({ duplicateWorkId: duplicate.workId, canonicalWorkId: canonical.workId });
        }
      }
    });
    return merged;
  }

  async #readAll(): Promise<WorkMap> {
    const value = (await browser.storage.session.get(STORAGE_KEY))[STORAGE_KEY];
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return {};
    const result: WorkMap = {};
    for (const [key, candidate] of Object.entries(value as Record<string, unknown>)) {
      if (isWorkRecord(candidate)) result[key] = candidate;
    }
    return result;
  }

  async #writeAll(value: WorkMap): Promise<void> {
    await browser.storage.session.set({ [STORAGE_KEY]: value });
  }

  async #mutate(mutator: (all: WorkMap) => void): Promise<void> {
    const operation = this.#writeTail.then(async () => {
      const all = await this.#readAll();
      mutator(all);
      await this.#writeAll(all);
    });
    this.#writeTail = operation.catch(() => undefined);
    await operation;
  }
}

function isWorkRecord(value: unknown): value is WorkRecord {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const work = value as Partial<WorkRecord>;
  return (
    typeof work.workId === 'string' &&
    typeof work.runtimeSessionId === 'string' &&
    typeof work.jobSignature === 'string' &&
    typeof work.sourceBinaryId === 'string' &&
    typeof work.sourceSha256 === 'string' &&
    typeof work.processingSpecFingerprint === 'string' &&
    typeof work.engineProfileFingerprint === 'string' &&
    typeof work.stage === 'string' &&
    typeof work.suppressCachePromotion === 'boolean' &&
    typeof work.attempt === 'number' &&
    typeof work.createdAt === 'number' &&
    typeof work.updatedAt === 'number' &&
    typeof work.sourceRaster === 'object' && work.sourceRaster !== null
  );
}
