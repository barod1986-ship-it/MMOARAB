import { openRuntimeDb } from '../binary/db.js';
import { leaseId } from '../binary/binary-store.js';
import type { BinaryLease, CacheEntry, CacheMetaRecord } from '../binary/schema.js';
import type { BinaryRef } from '../pipeline/types.js';
import {
  CACHE_PRESSURE_HIGH_RATIO,
  CACHE_PRESSURE_TARGET_RATIO,
  CACHE_TOUCH_COALESCE_MS
} from '../shared/constants.js';
import { CachePolicyStore, type CachePolicy } from './cache-policy.js';

const CACHE_META_KEY = 'cache-stats' as const;
const ALLOWED_RESULT_MIME = new Set(['image/png', 'image/webp']);

export type CacheHit = {
  cacheKey: string;
  result: BinaryRef;
  width: number;
  height: number;
};

export type CachePromotion = {
  cacheKey: string;
  sourceSha256: string;
  processingSpecFingerprint: string;
  engineProfileFingerprint: string;
  resultBinaryId: string;
  byteLength: number;
  mimeType: string;
  width: number;
  height: number;
};

export type CacheGcReport = {
  removedEntries: number;
  reclaimedLogicalBytes: number;
  remainingBytes: number;
  remainingEntries: number;
};

export type CacheStats = {
  approxBytes: number;
  approxEntries: number;
  lastGcAt?: number;
  lastFullRecountAt?: number;
};

export class ResultCache {
  readonly #policies: CachePolicyStore;

  constructor(policies = new CachePolicyStore()) {
    this.#policies = policies;
  }

  async lookup(input: {
    cacheKey: string;
    jobId: string;
    runtimeSessionId: string;
    now?: number;
  }): Promise<CacheHit | null> {
    const policy = await this.#policies.get();
    if (!policy.enabled) return null;
    const now = input.now ?? Date.now();
    const db = await openRuntimeDb();
    const tx = db.transaction(['cacheEntries', 'binaries', 'binaryLeases', 'meta'], 'readwrite');
    const cacheStore = tx.objectStore('cacheEntries');
    const binaryStore = tx.objectStore('binaries');
    const leaseStore = tx.objectStore('binaryLeases');
    const entry = await cacheStore.get(input.cacheKey);
    if (!entry) {
      await tx.done;
      return null;
    }

    const cacheLeaseId = leaseId(entry.resultBinaryId, 'cache', entry.cacheKey, 'cache');
    const cacheLease = await leaseStore.get(cacheLeaseId);
    const binary = await binaryStore.get(entry.resultBinaryId);
    const valid =
      entry.expiresAt > now &&
      Boolean(cacheLease) &&
      Boolean(binary) &&
      binary?.purpose === 'result' &&
      binary.byteLength === entry.byteLength &&
      binary.mimeType === entry.mimeType &&
      ALLOWED_RESULT_MIME.has(entry.mimeType) &&
      Number.isInteger(entry.width) && entry.width > 0 &&
      Number.isInteger(entry.height) && entry.height > 0;

    if (!valid) {
      await removeEntryInsideTransaction(tx, entry);
      await updateStatsFromEntries(tx, now, true);
      await tx.done;
      return null;
    }

    const deliveryLease: BinaryLease = {
      leaseId: leaseId(entry.resultBinaryId, 'job', input.jobId, 'delivery'),
      binaryId: entry.resultBinaryId,
      ownerType: 'job',
      ownerId: input.jobId,
      role: 'delivery',
      runtimeSessionId: input.runtimeSessionId,
      createdAt: now
    };
    await leaseStore.put(deliveryLease);
    if (now - entry.lastAccessedAt >= CACHE_TOUCH_COALESCE_MS) {
      entry.lastAccessedAt = now;
      await cacheStore.put(entry);
    }
    if (binary) {
      binary.lastTouchedAt = now;
      await binaryStore.put(binary);
    }
    await tx.done;
    return {
      cacheKey: entry.cacheKey,
      result: {
        binaryId: entry.resultBinaryId,
        store: 'indexeddb-transient',
        byteLength: entry.byteLength,
        mimeType: entry.mimeType,
        createdAt: binary?.createdAt ?? entry.createdAt
      },
      width: entry.width,
      height: entry.height
    };
  }

  async promote(input: CachePromotion): Promise<'cached' | 'skipped-quota' | 'disabled'> {
    const policy = await this.#policies.get();
    if (!policy.enabled) return 'disabled';
    if (!validPromotion(input)) return 'disabled';

    const pressure = await storagePressure();
    if (pressure !== null && pressure >= CACHE_PRESSURE_HIGH_RATIO) {
      await this.evictToBudget(Math.floor(policy.maxBytes * CACHE_PRESSURE_TARGET_RATIO));
    }

    try {
      await this.#promoteOnce(input, policy);
      await this.evictToBudget();
      return 'cached';
    } catch (error) {
      if (!isQuotaExceeded(error)) throw error;
      await this.evictToBudget(Math.floor(policy.maxBytes * policy.lowWaterRatio));
      try {
        await this.#promoteOnce(input, policy);
        await this.evictToBudget();
        return 'cached';
      } catch (retryError) {
        if (isQuotaExceeded(retryError)) return 'skipped-quota';
        throw retryError;
      }
    }
  }

  async evictToBudget(targetBytes?: number): Promise<CacheGcReport> {
    const policy = await this.#policies.get();
    const db = await openRuntimeDb();
    const now = Date.now();
    const tx = db.transaction(['cacheEntries', 'binaries', 'binaryLeases', 'meta'], 'readwrite');
    const entries = await tx.objectStore('cacheEntries').getAll();
    const total = entries.reduce((sum, entry) => sum + entry.byteLength, 0);
    const budget = Math.max(0, targetBytes ?? policy.maxBytes);
    const needsBudgetEviction = total > budget;
    // Default budget overflow drains to the configured low-water mark. Explicit
    // targets (storage pressure, quota retry, clear) are already the desired floor.
    const evictionTarget = targetBytes === undefined
      ? Math.floor(policy.maxBytes * policy.lowWaterRatio)
      : budget;
    let remaining = total;
    let removedEntries = 0;
    let reclaimedLogicalBytes = 0;

    const victims = [...entries].sort((a, b) => {
      const aExpired = a.expiresAt <= now ? 0 : 1;
      const bExpired = b.expiresAt <= now ? 0 : 1;
      return aExpired - bExpired || a.lastAccessedAt - b.lastAccessedAt || a.createdAt - b.createdAt || a.cacheKey.localeCompare(b.cacheKey);
    });

    for (const entry of victims) {
      const expired = entry.expiresAt <= now;
      const overTarget = needsBudgetEviction && remaining > evictionTarget;
      if (!expired && !overTarget) continue;
      await removeEntryInsideTransaction(tx, entry);
      remaining -= entry.byteLength;
      removedEntries += 1;
      reclaimedLogicalBytes += entry.byteLength;
    }

    const remainingEntries = await tx.objectStore('cacheEntries').count();
    const meta: CacheMetaRecord = {
      key: CACHE_META_KEY,
      approxBytes: Math.max(0, remaining),
      approxEntries: remainingEntries,
      lastGcAt: now,
      lastFullRecountAt: now
    };
    await tx.objectStore('meta').put(meta);
    await tx.done;
    return { removedEntries, reclaimedLogicalBytes, remainingBytes: Math.max(0, remaining), remainingEntries };
  }

  async clear(): Promise<CacheGcReport> {
    return await this.evictToBudget(0);
  }

  async getStats(): Promise<CacheStats> {
    const db = await openRuntimeDb();
    const meta = await db.get('meta', CACHE_META_KEY);
    if (meta && meta.approxBytes >= 0 && meta.approxEntries >= 0) return meta;
    return await this.recount();
  }

  async recount(): Promise<CacheStats> {
    const db = await openRuntimeDb();
    const tx = db.transaction(['cacheEntries', 'meta'], 'readwrite');
    const entries = await tx.objectStore('cacheEntries').getAll();
    const now = Date.now();
    const meta: CacheMetaRecord = {
      key: CACHE_META_KEY,
      approxBytes: entries.reduce((sum, entry) => sum + entry.byteLength, 0),
      approxEntries: entries.length,
      lastFullRecountAt: now
    };
    await tx.objectStore('meta').put(meta);
    await tx.done;
    return meta;
  }

  async #promoteOnce(input: CachePromotion, policy: CachePolicy): Promise<void> {
    const db = await openRuntimeDb();
    const now = Date.now();
    const tx = db.transaction(['cacheEntries', 'binaries', 'binaryLeases', 'meta'], 'readwrite');
    const binary = await tx.objectStore('binaries').get(input.resultBinaryId);
    if (!binary || binary.purpose !== 'result' || binary.byteLength !== input.byteLength || binary.mimeType !== input.mimeType) {
      await tx.done;
      throw new Error('Cache promotion rejected a missing or mismatched result binary.');
    }
    const existing = await tx.objectStore('cacheEntries').get(input.cacheKey);
    if (existing && existing.resultBinaryId !== input.resultBinaryId) {
      await removeEntryInsideTransaction(tx, existing);
    }
    const entry: CacheEntry = {
      cacheKey: input.cacheKey,
      sourceSha256: input.sourceSha256,
      processingSpecFingerprint: input.processingSpecFingerprint,
      engineProfileFingerprint: input.engineProfileFingerprint,
      resultBinaryId: input.resultBinaryId,
      byteLength: input.byteLength,
      mimeType: input.mimeType,
      width: input.width,
      height: input.height,
      createdAt: now,
      lastAccessedAt: now,
      expiresAt: now + policy.ttlMs
    };
    const cacheLease: BinaryLease = {
      leaseId: leaseId(input.resultBinaryId, 'cache', input.cacheKey, 'cache'),
      binaryId: input.resultBinaryId,
      ownerType: 'cache',
      ownerId: input.cacheKey,
      role: 'cache',
      createdAt: now
    };
    await tx.objectStore('cacheEntries').put(entry);
    await tx.objectStore('binaryLeases').put(cacheLease);
    await updateStatsFromEntries(tx, now, false);
    await tx.done;
  }
}

async function removeEntryInsideTransaction(tx: any, entry: CacheEntry): Promise<void> {
  const cacheStore = tx.objectStore('cacheEntries');
  const leaseStore = tx.objectStore('binaryLeases');
  const binaryStore = tx.objectStore('binaries');
  await cacheStore.delete(entry.cacheKey);
  await leaseStore.delete(leaseId(entry.resultBinaryId, 'cache', entry.cacheKey, 'cache'));
  if ((await leaseStore.index('by-binary-id').count(entry.resultBinaryId)) === 0) {
    await binaryStore.delete(entry.resultBinaryId);
  }
}

async function updateStatsFromEntries(tx: any, now: number, fullRecount: boolean): Promise<void> {
  const entries = await tx.objectStore('cacheEntries').getAll();
  const previous = await tx.objectStore('meta').get(CACHE_META_KEY);
  const meta: CacheMetaRecord = {
    key: CACHE_META_KEY,
    approxBytes: entries.reduce((sum: number, entry: CacheEntry) => sum + entry.byteLength, 0),
    approxEntries: entries.length,
    ...(previous?.lastGcAt ? { lastGcAt: previous.lastGcAt } : {}),
    ...(fullRecount ? { lastFullRecountAt: now } : previous?.lastFullRecountAt ? { lastFullRecountAt: previous.lastFullRecountAt } : {})
  };
  await tx.objectStore('meta').put(meta);
}

function validPromotion(input: CachePromotion): boolean {
  return (
    /^[a-f0-9]{64}$/.test(input.cacheKey) &&
    /^[a-f0-9]{64}$/.test(input.sourceSha256) &&
    input.byteLength > 0 &&
    ALLOWED_RESULT_MIME.has(input.mimeType) &&
    Number.isInteger(input.width) && input.width > 0 &&
    Number.isInteger(input.height) && input.height > 0
  );
}

async function storagePressure(): Promise<number | null> {
  try {
    const estimate = await navigator.storage?.estimate?.();
    if (!estimate?.quota || estimate.usage === undefined) return null;
    return estimate.usage / estimate.quota;
  } catch {
    return null;
  }
}

function isQuotaExceeded(error: unknown): boolean {
  return error instanceof DOMException ? error.name === 'QuotaExceededError' : (error as { name?: unknown } | null)?.name === 'QuotaExceededError';
}
