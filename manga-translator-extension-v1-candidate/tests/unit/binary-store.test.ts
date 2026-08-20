import 'fake-indexeddb/auto';
import { forceCloseDatabase } from 'fake-indexeddb';
import { unwrap } from 'idb';
import { afterEach, describe, expect, it } from 'vitest';
import { BinaryStore } from '../../src/binary/binary-store.js';
import { closeRuntimeDb, openRuntimeDb } from '../../src/binary/db.js';
import { RUNTIME_DB_NAME } from '../../src/shared/constants.js';

const bytes = new Uint8Array([0x89, 0x50, 0x4e, 0x47]);

async function resetDb(): Promise<void> {
  await closeRuntimeDb();
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.deleteDatabase(RUNTIME_DB_NAME);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error('Test IndexedDB deletion was blocked.'));
  });
}

afterEach(async () => {
  await resetDb();
});

describe('BinaryStore ownership and crash repair', () => {
  it('atomically stages a binary with its job lease and enforces owner access', async () => {
    const store = new BinaryStore();
    const ref = await store.stageOwned({
      blob: new Blob([bytes], { type: 'image/png' }),
      purpose: 'source',
      runtimeSessionId: 'run_current',
      lease: { ownerType: 'job', ownerId: 'job_1', role: 'source', runtimeSessionId: 'run_current' }
    });
    expect(await store.has(ref.binaryId)).toBe(true);
    expect((await store.get(ref.binaryId, { ownerType: 'job', ownerId: 'job_1', role: 'source' })).size).toBe(bytes.length);
    let denied = false;
    try {
      await store.get(ref.binaryId, { ownerType: 'job', ownerId: 'job_other', role: 'source' });
    } catch {
      denied = true;
    }
    expect(denied).toBe(true);
  });

  it('recovers the BinaryRef by owner/role after a simulated pointer-loss crash', async () => {
    const store = new BinaryStore();
    const staged = await store.stageOwned({
      blob: new Blob([bytes], { type: 'image/png' }),
      purpose: 'source',
      runtimeSessionId: 'run_current',
      lease: { ownerType: 'job', ownerId: 'job_recover', role: 'source', runtimeSessionId: 'run_current' }
    });
    const recovered = await store.findOwnedBinary('job', 'job_recover', 'source');
    expect(recovered?.binaryId).toBe(staged.binaryId);
  });

  it('reopens after an abnormal IndexedDB connection close and preserves the leased staged source', async () => {
    const store = new BinaryStore();
    const staged = await store.stageOwned({
      blob: new Blob([bytes], { type: 'image/png' }),
      purpose: 'source',
      runtimeSessionId: 'run_current',
      lease: { ownerType: 'job', ownerId: 'job_kill', role: 'source', runtimeSessionId: 'run_current' }
    });
    const db = await openRuntimeDb();
    forceCloseDatabase(unwrap(db));
    const recovered = await store.findOwnedBinary('job', 'job_kill', 'source');
    expect(recovered?.binaryId).toBe(staged.binaryId);
  });

  it('does not delete bytes while an independent delivery lease still exists', async () => {
    const store = new BinaryStore();
    const ref = await store.stageOwned({
      blob: new Blob([bytes], { type: 'image/png' }),
      purpose: 'result',
      runtimeSessionId: 'run_current',
      lease: { ownerType: 'job', ownerId: 'job_delivery', role: 'result', runtimeSessionId: 'run_current' }
    });
    await store.acquireLease({ binaryId: ref.binaryId, ownerType: 'job', ownerId: 'job_delivery', role: 'delivery', runtimeSessionId: 'run_current' });
    await store.releaseLease({ binaryId: ref.binaryId, ownerType: 'job', ownerId: 'job_delivery', role: 'result' });
    expect(await store.has(ref.binaryId)).toBe(true);
    await store.releaseLease({ binaryId: ref.binaryId, ownerType: 'job', ownerId: 'job_delivery', role: 'delivery' });
    expect(await store.has(ref.binaryId)).toBe(false);
  });

  it('drops stale runtime-session leases and orphan binaries but preserves cache-owned bytes', async () => {
    const store = new BinaryStore();
    const stale = await store.stageOwned({
      blob: new Blob([bytes], { type: 'image/png' }),
      purpose: 'source',
      runtimeSessionId: 'run_old',
      lease: { ownerType: 'job', ownerId: 'job_old', role: 'source', runtimeSessionId: 'run_old' }
    });
    const cache = await store.stageOwned({
      blob: new Blob([bytes], { type: 'image/png' }),
      purpose: 'result',
      lease: { ownerType: 'cache', ownerId: 'cache_1', role: 'cache' }
    });
    const orphan = await store.put({ blob: new Blob([bytes], { type: 'image/png' }), purpose: 'source', runtimeSessionId: 'run_old' });
    const report = await store.reconcileRuntimeSession('run_current');
    expect(report.releasedLeases).toBe(1);
    expect(await store.has(stale.binaryId)).toBe(false);
    expect(await store.has(orphan.binaryId)).toBe(false);
    expect(await store.has(cache.binaryId)).toBe(true);
  });
});
