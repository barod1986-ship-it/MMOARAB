import { AppError } from '../core/errors.js';
import { newBinaryId } from '../shared/ids.js';
import { MAX_RESULT_BYTES, MAX_SOURCE_BYTES } from '../shared/constants.js';
import type { BinaryLeaseRole, BinaryOwnerRef, BinaryOwnerType, BinaryPurpose, BinaryRef } from '../pipeline/types.js';
import { openRuntimeDb } from './db.js';
import type { BinaryLease, BinaryRecord } from './schema.js';

export type InitialBinaryLease = BinaryOwnerRef & { runtimeSessionId?: string };

export class BinaryStore {
  async put(input: { blob: Blob; purpose: BinaryPurpose; runtimeSessionId?: string }): Promise<BinaryRef> {
    const record = createRecord(input);
    try {
      const db = await openRuntimeDb();
      await db.put('binaries', record);
      return refFromRecord(record);
    } catch (cause) {
      throw new AppError('BINARY_STORE_FAILED', 'Failed to persist binary payload.', { cause });
    }
  }

  async stageOwned(input: {
    blob: Blob;
    purpose: BinaryPurpose;
    runtimeSessionId?: string;
    lease: InitialBinaryLease;
  }): Promise<BinaryRef> {
    const record = createRecord(input);
    const lease = createLease(record.binaryId, input.lease);
    try {
      const db = await openRuntimeDb();
      const tx = db.transaction(['binaries', 'binaryLeases'], 'readwrite');
      await Promise.all([tx.objectStore('binaries').put(record), tx.objectStore('binaryLeases').put(lease)]);
      await tx.done;
      return refFromRecord(record);
    } catch (cause) {
      throw new AppError('BINARY_STORE_FAILED', 'Failed to atomically stage binary and ownership lease.', { cause });
    }
  }

  async get(binaryId: string, owner: BinaryOwnerRef): Promise<Blob> {
    const db = await openRuntimeDb();
    const tx = db.transaction(['binaries', 'binaryLeases'], 'readwrite');
    const lease = await tx.objectStore('binaryLeases').get(leaseId(binaryId, owner.ownerType, owner.ownerId, owner.role));
    if (!lease) {
      await tx.done;
      throw new AppError('BINARY_ACCESS_DENIED', 'Binary access requires a matching ownership lease.');
    }
    const store = tx.objectStore('binaries');
    const record = await store.get(binaryId);
    if (!record) {
      await tx.done;
      throw new AppError('BINARY_NOT_FOUND', 'Binary record referenced by lease no longer exists.');
    }
    record.lastTouchedAt = Date.now();
    await store.put(record);
    await tx.done;
    return record.blob;
  }

  async attachHash(binaryId: string, sha256: string): Promise<BinaryRef> {
    if (!/^[a-f0-9]{64}$/.test(sha256)) throw new AppError('HASH_FAILED', 'Invalid SHA-256 encoding.');
    const db = await openRuntimeDb();
    const tx = db.transaction('binaries', 'readwrite');
    const record = await tx.store.get(binaryId);
    if (!record) {
      await tx.done;
      throw new AppError('BINARY_NOT_FOUND', 'Cannot attach hash to a missing binary.');
    }
    record.sha256 = sha256;
    record.lastTouchedAt = Date.now();
    await tx.store.put(record);
    await tx.done;
    return refFromRecord(record);
  }

  async acquireLease(input: {
    binaryId: string;
    ownerType: BinaryOwnerType;
    ownerId: string;
    role: BinaryLeaseRole;
    runtimeSessionId?: string;
  }): Promise<void> {
    const db = await openRuntimeDb();
    const tx = db.transaction(['binaries', 'binaryLeases'], 'readwrite');
    if (!(await tx.objectStore('binaries').get(input.binaryId))) {
      await tx.done;
      throw new AppError('BINARY_NOT_FOUND', 'Cannot lease a missing binary.');
    }
    await tx.objectStore('binaryLeases').put(createLease(input.binaryId, input));
    await tx.done;
  }

  async releaseLease(input: {
    binaryId: string;
    ownerType: BinaryOwnerType;
    ownerId: string;
    role: BinaryLeaseRole;
  }): Promise<void> {
    const db = await openRuntimeDb();
    const tx = db.transaction(['binaries', 'binaryLeases'], 'readwrite');
    const leases = tx.objectStore('binaryLeases');
    await leases.delete(leaseId(input.binaryId, input.ownerType, input.ownerId, input.role));
    const remaining = await leases.index('by-binary-id').count(input.binaryId);
    if (remaining === 0) await tx.objectStore('binaries').delete(input.binaryId);
    await tx.done;
  }

  async releaseOwner(ownerType: BinaryOwnerType, ownerId: string): Promise<void> {
    const db = await openRuntimeDb();
    const tx = db.transaction(['binaries', 'binaryLeases'], 'readwrite');
    const leasesStore = tx.objectStore('binaryLeases');
    const leases = await leasesStore.index('by-owner').getAll([ownerType, ownerId]);
    const binaryIds = new Set<string>();
    for (const lease of leases) {
      binaryIds.add(lease.binaryId);
      await leasesStore.delete(lease.leaseId);
    }
    for (const binaryId of binaryIds) {
      if ((await leasesStore.index('by-binary-id').count(binaryId)) === 0) {
        await tx.objectStore('binaries').delete(binaryId);
      }
    }
    await tx.done;
  }

  async findOwnedBinary(ownerType: BinaryOwnerType, ownerId: string, role: BinaryLeaseRole): Promise<BinaryRef | null> {
    const db = await openRuntimeDb();
    const tx = db.transaction(['binaries', 'binaryLeases'], 'readonly');
    const leases = await tx.objectStore('binaryLeases').index('by-owner-role').getAll([ownerType, ownerId, role]);
    const lease = leases[0];
    if (!lease) {
      await tx.done;
      return null;
    }
    const record = await tx.objectStore('binaries').get(lease.binaryId);
    await tx.done;
    return record ? refFromRecord(record) : null;
  }

  async has(binaryId: string): Promise<boolean> {
    return Boolean(await (await openRuntimeDb()).get('binaries', binaryId));
  }

  async reconcileRuntimeSession(currentRuntimeSessionId: string): Promise<{ releasedLeases: number; deletedBinaries: number }> {
    const db = await openRuntimeDb();
    const tx = db.transaction(['binaries', 'binaryLeases'], 'readwrite');
    const leasesStore = tx.objectStore('binaryLeases');
    const allLeases = await leasesStore.getAll();
    let releasedLeases = 0;
    for (const lease of allLeases) {
      if (lease.ownerType === 'cache') continue;
      if (lease.runtimeSessionId && lease.runtimeSessionId !== currentRuntimeSessionId) {
        await leasesStore.delete(lease.leaseId);
        releasedLeases += 1;
      }
    }

    let deletedBinaries = 0;
    const binariesStore = tx.objectStore('binaries');
    const binaries = await binariesStore.getAll();
    for (const binary of binaries) {
      const count = await leasesStore.index('by-binary-id').count(binary.binaryId);
      if (count === 0) {
        await binariesStore.delete(binary.binaryId);
        deletedBinaries += 1;
      }
    }
    await tx.done;
    return { releasedLeases, deletedBinaries };
  }
}

function createRecord(input: { blob: Blob; purpose: BinaryPurpose; runtimeSessionId?: string }): BinaryRecord {
  const limit = input.purpose === 'source' ? MAX_SOURCE_BYTES : MAX_RESULT_BYTES;
  if (input.blob.size <= 0) throw new AppError('NOT_AN_IMAGE', 'Cannot store an empty binary payload.');
  if (input.blob.size > limit) {
    throw new AppError(input.purpose === 'source' ? 'SOURCE_TOO_LARGE' : 'RESULT_TOO_LARGE', 'Binary payload exceeds the V1 32 MiB guard.', {
      details: { bytes: input.blob.size, limit }
    });
  }
  const mimeType = normalizeMime(input.blob.type);
  if (!mimeType) throw new AppError('NOT_AN_IMAGE', 'Binary payload must carry a normalized image MIME type before staging.');
  const now = Date.now();
  return {
    binaryId: newBinaryId(),
    purpose: input.purpose,
    blob: input.blob,
    byteLength: input.blob.size,
    mimeType,
    ...(input.runtimeSessionId ? { runtimeSessionId: input.runtimeSessionId } : {}),
    createdAt: now,
    lastTouchedAt: now
  };
}

function createLease(binaryId: string, input: InitialBinaryLease): BinaryLease {
  return {
    leaseId: leaseId(binaryId, input.ownerType, input.ownerId, input.role),
    binaryId,
    ownerType: input.ownerType,
    ownerId: input.ownerId,
    role: input.role,
    ...(input.runtimeSessionId ? { runtimeSessionId: input.runtimeSessionId } : {}),
    createdAt: Date.now()
  };
}

export function leaseId(binaryId: string, ownerType: BinaryOwnerType, ownerId: string, role: BinaryLeaseRole): string {
  return `lease:v1:${binaryId}:${ownerType}:${ownerId}:${role}`;
}

function refFromRecord(record: BinaryRecord): BinaryRef {
  return {
    binaryId: record.binaryId,
    store: 'indexeddb-transient',
    byteLength: record.byteLength,
    mimeType: record.mimeType,
    createdAt: record.createdAt,
    ...(record.sha256 ? { sha256: record.sha256 } : {})
  };
}

function normalizeMime(value: string): string {
  return value.split(';', 1)[0]?.trim().toLowerCase() ?? '';
}
