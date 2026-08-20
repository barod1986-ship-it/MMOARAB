import { browser } from 'wxt/browser';
import { newRuntimeSessionId } from '../shared/ids.js';

const STORAGE_KEY = 'phase3.runtimeSession';

type RuntimeSessionRecord = {
  runtimeSessionId: string;
  createdAt: number;
};

export class RuntimeSessionStore {
  #cached: RuntimeSessionRecord | null = null;
  #initializing: Promise<RuntimeSessionRecord> | null = null;

  async getOrCreate(): Promise<RuntimeSessionRecord> {
    if (this.#cached) return this.#cached;
    if (this.#initializing) return await this.#initializing;
    this.#initializing = this.#loadOrCreate();
    try {
      this.#cached = await this.#initializing;
      return this.#cached;
    } finally {
      this.#initializing = null;
    }
  }

  async #loadOrCreate(): Promise<RuntimeSessionRecord> {
    const current = (await browser.storage.session.get(STORAGE_KEY))[STORAGE_KEY];
    if (isRuntimeSessionRecord(current)) return current;
    const created: RuntimeSessionRecord = { runtimeSessionId: newRuntimeSessionId(), createdAt: Date.now() };
    await browser.storage.session.set({ [STORAGE_KEY]: created });
    return created;
  }
}

function isRuntimeSessionRecord(value: unknown): value is RuntimeSessionRecord {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const candidate = value as Partial<RuntimeSessionRecord>;
  return typeof candidate.runtimeSessionId === 'string' && candidate.runtimeSessionId.startsWith('run_') && typeof candidate.createdAt === 'number';
}
