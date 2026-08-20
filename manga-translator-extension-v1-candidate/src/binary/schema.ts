import type { DBSchema } from 'idb';
import type { BinaryLeaseRole, BinaryOwnerType, BinaryPurpose } from '../pipeline/types.js';

export type BinaryRecord = {
  binaryId: string;
  purpose: BinaryPurpose;
  blob: Blob;
  byteLength: number;
  mimeType: string;
  sha256?: string;
  runtimeSessionId?: string;
  createdAt: number;
  lastTouchedAt: number;
};

export type BinaryLease = {
  leaseId: string;
  binaryId: string;
  ownerType: BinaryOwnerType;
  ownerId: string;
  role: BinaryLeaseRole;
  runtimeSessionId?: string;
  createdAt: number;
};

export type CacheEntry = {
  cacheKey: string;
  sourceSha256: string;
  processingSpecFingerprint: string;
  engineProfileFingerprint: string;
  resultBinaryId: string;
  byteLength: number;
  mimeType: string;
  width: number;
  height: number;
  createdAt: number;
  lastAccessedAt: number;
  expiresAt: number;
};

export type CacheMetaRecord = {
  key: 'cache-stats';
  approxBytes: number;
  approxEntries: number;
  lastGcAt?: number;
  lastFullRecountAt?: number;
};

export interface MangaRuntimeDb extends DBSchema {
  binaries: {
    key: string;
    value: BinaryRecord;
    indexes: {
      'by-purpose': BinaryPurpose;
      'by-runtime-session': string;
      'by-last-touched': number;
    };
  };
  binaryLeases: {
    key: string;
    value: BinaryLease;
    indexes: {
      'by-binary-id': string;
      'by-owner': [BinaryOwnerType, string];
      'by-owner-role': [BinaryOwnerType, string, BinaryLeaseRole];
      'by-runtime-session': string;
    };
  };
  cacheEntries: {
    key: string;
    value: CacheEntry;
    indexes: {
      'by-expires-at': number;
      'by-last-accessed': number;
    };
  };
  meta: {
    key: string;
    value: CacheMetaRecord;
  };
}
