import { openDB, type IDBPDatabase } from 'idb';
import { RUNTIME_DB_NAME, RUNTIME_DB_VERSION } from '../shared/constants.js';
import type { MangaRuntimeDb } from './schema.js';

let databasePromise: Promise<IDBPDatabase<MangaRuntimeDb>> | null = null;

export function openRuntimeDb(): Promise<IDBPDatabase<MangaRuntimeDb>> {
  if (databasePromise) return databasePromise;
  databasePromise = openDB<MangaRuntimeDb>(RUNTIME_DB_NAME, RUNTIME_DB_VERSION, {
    upgrade(db, oldVersion) {
      if (oldVersion < 1) {
        const binaries = db.createObjectStore('binaries', { keyPath: 'binaryId' });
        binaries.createIndex('by-purpose', 'purpose');
        binaries.createIndex('by-runtime-session', 'runtimeSessionId');
        binaries.createIndex('by-last-touched', 'lastTouchedAt');

        const leases = db.createObjectStore('binaryLeases', { keyPath: 'leaseId' });
        leases.createIndex('by-binary-id', 'binaryId');
        leases.createIndex('by-owner', ['ownerType', 'ownerId']);
        leases.createIndex('by-owner-role', ['ownerType', 'ownerId', 'role']);
        leases.createIndex('by-runtime-session', 'runtimeSessionId');

        const cache = db.createObjectStore('cacheEntries', { keyPath: 'cacheKey' });
        cache.createIndex('by-expires-at', 'expiresAt');
        cache.createIndex('by-last-accessed', 'lastAccessedAt');
        db.createObjectStore('meta', { keyPath: 'key' });
      }
    },
    blocked(currentVersion, blockedVersion) {
      console.warn('[mte] IndexedDB upgrade blocked by another extension context', { currentVersion, blockedVersion });
    },
    blocking() {
      void closeRuntimeDb();
    },
    terminated() {
      databasePromise = null;
    }
  });
  return databasePromise;
}

export async function closeRuntimeDb(): Promise<void> {
  const pending = databasePromise;
  databasePromise = null;
  if (!pending) return;
  try {
    (await pending).close();
  } catch {
    // Connection may already be terminated.
  }
}
