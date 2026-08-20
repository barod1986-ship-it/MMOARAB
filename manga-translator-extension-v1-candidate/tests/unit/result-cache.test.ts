import 'fake-indexeddb/auto';
import { afterEach, describe, expect, it } from 'vitest';
import { BinaryStore } from '../../src/binary/binary-store.js';
import { closeRuntimeDb, openRuntimeDb } from '../../src/binary/db.js';
import { ResultCache } from '../../src/cache/result-cache.js';
import type { CachePolicyStore } from '../../src/cache/cache-policy.js';

const policy = {
  enabled: true,
  maxBytes: 256 * 1024 * 1024,
  ttlMs: 30 * 24 * 60 * 60 * 1000,
  lowWaterRatio: 0.8
};

function cache(): ResultCache {
  return new ResultCache({ get: async () => ({ ...policy }) } as CachePolicyStore);
}

afterEach(async () => {
  await closeRuntimeDb();
  await deleteRuntimeDatabase();
});

describe('persistent result cache', () => {
  it('keeps current delivery bytes alive when cache is cleared', async () => {
    const binaries = new BinaryStore();
    const result = await binaries.stageOwned({
      blob: new Blob([new Uint8Array([1, 2, 3, 4])], { type: 'image/png' }),
      purpose: 'result',
      runtimeSessionId: 'run-1',
      lease: { ownerType: 'work', ownerId: 'work-1', role: 'result', runtimeSessionId: 'run-1' }
    });
    const store = cache();
    const cacheKey = 'c'.repeat(64);
    await store.promote({
      cacheKey,
      sourceSha256: 'a'.repeat(64),
      processingSpecFingerprint: 'b'.repeat(64),
      engineProfileFingerprint: 'engine-v1',
      resultBinaryId: result.binaryId,
      byteLength: result.byteLength,
      mimeType: result.mimeType,
      width: 100,
      height: 200
    });
    const hit = await store.lookup({ cacheKey, jobId: 'job-1', runtimeSessionId: 'run-1' });
    expect(hit?.result.binaryId).toBe(result.binaryId);
    await store.clear();
    const stillDeliverable = await binaries.get(result.binaryId, { ownerType: 'job', ownerId: 'job-1', role: 'delivery' });
    expect(stillDeliverable.size).toBe(4);
    await binaries.releaseOwner('job', 'job-1');
    await binaries.releaseOwner('work', 'work-1');
    expect(await binaries.has(result.binaryId)).toBe(false);
  });

  it('self-heals an entry whose result binary is missing', async () => {
    const binaries = new BinaryStore();
    const result = await binaries.stageOwned({
      blob: new Blob([new Uint8Array([5, 6, 7])], { type: 'image/png' }),
      purpose: 'result',
      runtimeSessionId: 'run-1',
      lease: { ownerType: 'work', ownerId: 'work-2', role: 'result', runtimeSessionId: 'run-1' }
    });
    const store = cache();
    const cacheKey = 'd'.repeat(64);
    await store.promote({
      cacheKey,
      sourceSha256: 'e'.repeat(64),
      processingSpecFingerprint: 'f'.repeat(64),
      engineProfileFingerprint: 'engine-v1',
      resultBinaryId: result.binaryId,
      byteLength: result.byteLength,
      mimeType: result.mimeType,
      width: 10,
      height: 20
    });
    const db = await openRuntimeDb();
    await db.delete('binaries', result.binaryId);
    expect(await store.lookup({ cacheKey, jobId: 'job-2', runtimeSessionId: 'run-1' })).toBeNull();
    expect(await db.get('cacheEntries', cacheKey)).toBe(undefined);
  });

  it('survives a runtime-session restart while transient work leases are collected', async () => {
    const binaries = new BinaryStore();
    const result = await binaries.stageOwned({
      blob: new Blob([new Uint8Array([9, 9, 9])], { type: 'image/png' }),
      purpose: 'result',
      runtimeSessionId: 'run-old',
      lease: { ownerType: 'work', ownerId: 'work-old', role: 'result', runtimeSessionId: 'run-old' }
    });
    const store = cache();
    const cacheKey = '1'.repeat(64);
    await store.promote({
      cacheKey,
      sourceSha256: '2'.repeat(64),
      processingSpecFingerprint: '3'.repeat(64),
      engineProfileFingerprint: 'engine-v1',
      resultBinaryId: result.binaryId,
      byteLength: result.byteLength,
      mimeType: result.mimeType,
      width: 30,
      height: 40
    });
    await binaries.reconcileRuntimeSession('run-new');
    const hit = await store.lookup({ cacheKey, jobId: 'job-new', runtimeSessionId: 'run-new' });
    expect(hit?.result.binaryId).toBe(result.binaryId);
  });
});


async function deleteRuntimeDatabase(): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.deleteDatabase('manga-translation-runtime');
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error ?? new Error('IndexedDB test cleanup failed.'));
    request.onblocked = () => reject(new Error('IndexedDB test cleanup was blocked by an open connection.'));
  });
}
