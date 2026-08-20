import { browser } from 'wxt/browser';
import { CACHE_DEFAULT_MAX_BYTES, CACHE_LOW_WATER_RATIO, CACHE_TTL_MS } from '../shared/constants.js';

const STORAGE_KEY = 'phase3.cachePolicy';

export type CachePolicy = {
  enabled: boolean;
  maxBytes: number;
  ttlMs: number;
  lowWaterRatio: number;
};

export const DEFAULT_CACHE_POLICY: CachePolicy = {
  enabled: true,
  maxBytes: CACHE_DEFAULT_MAX_BYTES,
  ttlMs: CACHE_TTL_MS,
  lowWaterRatio: CACHE_LOW_WATER_RATIO
};

export class CachePolicyStore {
  async get(): Promise<CachePolicy> {
    const raw = (await browser.storage.local.get(STORAGE_KEY))[STORAGE_KEY];
    if (!isCachePolicy(raw)) return structuredClone(DEFAULT_CACHE_POLICY);
    return raw;
  }

  async set(policy: CachePolicy): Promise<void> {
    if (!isCachePolicy(policy)) throw new Error('Invalid cache policy.');
    await browser.storage.local.set({ [STORAGE_KEY]: structuredClone(policy) });
  }
}

function isCachePolicy(value: unknown): value is CachePolicy {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const candidate = value as Partial<CachePolicy>;
  return (
    typeof candidate.enabled === 'boolean' &&
    typeof candidate.maxBytes === 'number' && candidate.maxBytes >= 0 &&
    typeof candidate.ttlMs === 'number' && candidate.ttlMs > 0 &&
    typeof candidate.lowWaterRatio === 'number' && candidate.lowWaterRatio > 0 && candidate.lowWaterRatio < 1
  );
}
