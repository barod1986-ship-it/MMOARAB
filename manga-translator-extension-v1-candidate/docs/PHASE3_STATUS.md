# Phase 3 — Queue / Work Dedupe / Persistent Result Cache Status

Implementation target: REV10 `06_STATE_CACHE_QUEUE.md` and Phase 3 exit criteria in `08_FINAL_EXTENSION_ARCHITECTURE.md`.

## Implemented

### Admission and scheduling

- Heavy acquisition begins only after a persisted `JobRecord` reaches admission.
- Priority bands P0–P6 are implemented: explicit, visible-current, visible-other, near-current, near-other, prefetch, far/discovered.
- P6/far is metadata-only by default and is not admitted unless explicitly requested.
- Fairness inside a band round-robins PageSessions while retaining per-session reading order.
- Non-visible/non-explicit prepared work is capped at 3 per PageSession; explicit/visible work bypasses that prepared-ahead gate.
- Lane defaults: acquisition 2, hash 1, mock engine 1, result staging 1, delivery 2. Phase 1 retains one global screenshot lane with >=550 ms between capture starts.

### Job / Work separation and dedupe

- `JobRecord` is a page-target consumer; `WorkRecord` is the unique processing execution.
- Final WorkSignature uses source SHA-256 + ProcessingSpec fingerprint + engine profile fingerprint.
- Work IDs for newly-created Phase 3 work are deterministic from the canonical WorkSignature.
- A source Work lease is acquired before a new WorkRecord is published; this step is idempotent across worker death.
- Existing live WorkRecords are joined instead of reprocessing identical final signatures.
- Duplicate WorkRecords from an older/interrupted state are reconciled to one canonical record when safe.
- Defensive fan-out is capped at 256 consumers per Work; overflow consumers are failed and are not hydrated afterward.

### Memory admission

- Extension-side soft live-materialization budget is 64 MiB.
- Unknown-size reservations default to 8 MiB.
- Hashing reserves source byte length as additional headroom.
- The temporary Phase 3 in-extension mock reserves estimated decoded raster surfaces and runs an over-budget item exclusively.
- Final delivery reserves result byte length while the Blob is materialized/sent.
- Persistent IndexedDB Blobs are not counted merely because they exist on disk.

### Persistent result cache

- Cache uses the existing REV10 IndexedDB V1 stores: `cacheEntries`, `binaries`, `binaryLeases`, and `meta`; no schema bump is required.
- Cache key namespace is `mte-result-cache-v1` and is based on source SHA-256 + ProcessingSpec fingerprint + engine profile fingerprint.
- Only validated final raster results are promoted; source images and semantic/provider data are not cached.
- Promotion reuses the same result binary and attaches a `cache/cache` lease rather than copying the Blob.
- Lookup validates expiry, cache lease, binary existence, byte length, MIME, and dimensions before attaching a temporary `job/delivery` lease.
- Broken/missing cache entries self-heal to misses.
- Cache defaults: enabled, 256 MiB max, 30-day TTL, 0.80 low-water ratio, 10-minute touch coalescing.
- GC removes expired entries first, then deterministic LRU victims until low-water when over budget.
- `navigator.storage.estimate()` is used only as a pressure signal; >=85% triggers more aggressive GC toward ~70% of configured cache budget when practical.
- `QuotaExceededError` triggers targeted GC + one promotion retry; a second quota failure skips caching but does not fail the already-valid result delivery.
- No `unlimitedStorage` and no `navigator.storage.persist()` are requested.

### Retry wake and MV3 recovery

- Retry scheduling persists compact `attempt`, `notBefore`, and error metadata; error taxonomy/retry ownership remains for Phase 7.
- One shared alarm named `queue-wake` represents the earliest future deadline.
- Deferred alarm scheduling is floored at 30 seconds and does not use long timers.
- No alarm-per-image design.
- Baseline Chrome 148 does not use `persistAcrossSessions`; startup reconciliation recreates the alarm when current-session pending deadlines exist.
- `storage.session` Job/Work state is session-scoped and disappears across browser restart; cache leases/binaries remain persistent in IndexedDB.
- Reconciliation repairs pointer/lease gaps that can occur when a worker dies between IndexedDB and `storage.session` checkpoints.

## Phase 3 tests/checks added

- `tests/phase3-offline-runner.mjs`
  - cache-key identity;
  - priority invariants;
  - 120-candidate Webtoon admission bound;
  - cross-session round-robin fairness;
  - 64 MiB memory backpressure + exclusive large item;
  - deterministic Work ID from final signature.
- `tests/unit/queue-phase3.test.ts`
  - far candidate admission behavior;
  - large-item memory exclusivity.
- `tests/unit/result-cache.test.ts` (requires `fake-indexeddb`)
  - clearing cache preserves a current delivery lease;
  - broken cache entry self-heals;
  - cache survives runtime-session replacement while transient Work leases are collected.
- `scripts/verify-phase3-contracts.mjs`
  - alarms permission/name and Chrome 148 compatibility;
  - cache/memory/prepared-ahead defaults;
  - Work dedupe and deterministic owner ID;
  - source-lease-before-Work publication;
  - fan-out overflow exclusion;
  - cache lease/quota behavior;
  - lane caps;
  - no long Service Worker retry timers;
  - Phase 3 manifest version.

## Checks completed in this environment

Passed:

- strict structural TypeScript check for all source/tests using local structural declarations;
- 15 dependency-free Phase 1 checks;
- 5 dependency-free Phase 2 identity/delivery checks;
- 6 dependency-free Phase 3 queue/cache-identity checks;
- 20 Phase 3 contract checks;
- source scan confirms no `persistAcrossSessions` use in the Chrome 148 baseline and no long retry timer in background/queue scheduling.

Not executable here:

- real Vitest + `fake-indexeddb` suite;
- WXT typecheck/build/manifest output gate;
- Chrome 148+ extension execution and Service Worker kill/wake browser test.

Reason: npm registry access did not complete in this runtime (the final `npm install --package-lock-only` attempt timed out), no `node_modules`/lockfile is available, and the installed local Chromium is 144.0.7559.96 rather than the required Chrome 148+ baseline.

No fake `package-lock.json` or fabricated browser/build pass was produced.

## Phase 3 exit criteria

| REV10 exit criterion | Status |
|---|---|
| 100+ fixture candidates do not explode memory | Implemented and dependency-free 120-candidate admission/memory checks pass; real Chrome memory profiling still belongs to the browser gate |
| repeated identical content dedupes | Implemented through final WorkSignature → one live WorkRecord, plus persistent cache reuse |
| cache survives restart | Design/IndexedDB lease path implemented and a `fake-indexeddb` test exists; real dependency/browser execution remains blocked by this environment |

## Deferred to Phase 4

The local Engine protocol shell is intentionally not implemented here. Phase 4 owns loopback server/auth/pairing/capabilities/durable engine jobs/spool/idempotency/status/cancel/result/security tests. The current `MockProcessingGateway` remains a deterministic raster fixture only.
