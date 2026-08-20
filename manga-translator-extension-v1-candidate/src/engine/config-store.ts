import { browser } from 'wxt/browser';

const STORAGE_KEY = 'engine.connection.v1';

type StoredEngineConnection = {
  schemaVersion: 1;
  token: string;
  pairedAt: number;
  engineVersion?: string;
  profileId?: string;
  profileFingerprint?: string;
};

export class EngineConnectionStore {
  #tail: Promise<void> = Promise.resolve();

  async get(): Promise<StoredEngineConnection | null> {
    await this.#tail;
    const raw = (await browser.storage.local.get(STORAGE_KEY))[STORAGE_KEY];
    if (!isStoredConnection(raw)) return null;
    return structuredClone(raw);
  }

  async save(input: Omit<StoredEngineConnection, 'schemaVersion' | 'pairedAt'>): Promise<void> {
    const value: StoredEngineConnection = {
      schemaVersion: 1,
      token: input.token,
      pairedAt: Date.now(),
      ...(input.engineVersion ? { engineVersion: input.engineVersion } : {}),
      ...(input.profileId ? { profileId: input.profileId } : {}),
      ...(input.profileFingerprint ? { profileFingerprint: input.profileFingerprint } : {})
    };
    await this.#mutate(async () => await browser.storage.local.set({ [STORAGE_KEY]: value }));
  }

  async updateProfile(input: { engineVersion: string; profileId: string; profileFingerprint: string }): Promise<void> {
    const current = await this.get();
    if (!current) return;
    await this.#mutate(async () => await browser.storage.local.set({
      [STORAGE_KEY]: {
        ...current,
        engineVersion: input.engineVersion,
        profileId: input.profileId,
        profileFingerprint: input.profileFingerprint
      }
    }));
  }

  async clear(): Promise<void> {
    await this.#mutate(async () => await browser.storage.local.remove(STORAGE_KEY));
  }

  async #mutate(operation: () => Promise<void>): Promise<void> {
    const next = this.#tail.then(operation);
    this.#tail = next.catch(() => undefined);
    await next;
  }
}

function isStoredConnection(value: unknown): value is StoredEngineConnection {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const candidate = value as Partial<StoredEngineConnection>;
  return candidate.schemaVersion === 1 && typeof candidate.token === 'string' && candidate.token.length >= 20 && typeof candidate.pairedAt === 'number';
}
