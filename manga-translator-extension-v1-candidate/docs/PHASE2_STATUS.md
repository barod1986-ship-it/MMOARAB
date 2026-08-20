# Phase 2 — BinaryStore + Pipeline Identity Status

Implementation target: REV10 `03_PROCESSING_PIPELINE.md`, the BinaryStore/lease contracts finalized in `06_STATE_CACHE_QUEUE.md`, and Phase 2 exit criteria in `08_FINAL_EXTENSION_ARCHITECTURE.md`.

## Implemented

- Trusted pipeline intake after Phase 1 acquisition; the Content Script can submit only its current `sessionId`, `candidateId`, `sourceRevision`, and bounded acquired image payload.
- Source validation re-decodes/sniffs bytes in the trusted path and accepts only JPEG/PNG/WebP/AVIF with a valid acquisition-method/authority pair.
- 32 MiB source/result guards are enforced before durable staging.
- IndexedDB database name is exactly `manga-translation-runtime`, integer schema version 1.
- V1 stores are `binaries`, `binaryLeases`, `cacheEntries`, and `meta`; `cacheEntries`/`meta` are schema placeholders only until Phase 3.
- `binaries` stores opaque random `binaryId`, purpose, Blob, size, normalized MIME, optional SHA-256, runtime session, and timestamps.
- `binaryLeases` is a separate ownership table with deterministic idempotent lease IDs and the REV10 indexes: by binary, owner, owner+role, and runtime session.
- Source and result staging use one IndexedDB transaction for `binary + lease`, then a separate `storage.session` pointer checkpoint. Recovery can reattach a lost pointer through `(ownerType, ownerId, role)`.
- Source SHA-256 is computed after durable staging using Web Crypto, then attached to the BinaryRef.
- Immutable V1 `ProcessingSpec` is frozen to `en → ar`, dialogue/narration translation, `sfxAction=preserve-original`, `uncertainAction=preserve-original`, revision `sfx-preserve-v1`, dimension-preserving translated raster output.
- Canonical ProcessingSpec serialization, separate ProcessingSpec fingerprint, and versioned WorkSignature based on source SHA-256 + canonical spec + engine profile fingerprint.
- `JobRecord` checkpoints use `storage.session`; binary payloads never use `storage.local`/`storage.session`.
- `storage.session`, `storage.local`, and `storage.sync` are explicitly restricted to `TRUSTED_CONTEXTS` where used.
- Runtime-session identity survives MV3 worker sleep through `storage.session`; a browser restart creates a new runtime session and reconciliation removes stale non-cache leases/orphan transient binaries.
- Deterministic Phase 2 mock gateway reads only a leased BinaryRef, decodes it, renders the same dimensions, and emits PNG with `mock-png-lossless-v1` semantics. It has no Engine URL/network endpoint.
- Result staging persists result metadata before the IDB handoff, then stages `result binary + job/result lease` atomically and repairs a pointer-loss crash through `by-owner-role`.
- Before final delivery, the coordinator validates persisted result size/MIME/dimensions and acquires an independent `job/delivery` lease.
- Final delivery rechecks active PageSession, tab, document, candidate, and exact `sourceRevision`. Stale results are never sent to the page.
- Content Script receives one bounded final Blob plus display metadata, applies/decodes it, rechecks target revision, and ACKs `applied`, `stale`, or `failed`.
- Content Script messages expose no arbitrary `binaryId`, ProcessingSpec, or engine profile fingerprint.
- A reused `<img>`/iframe node whose logical source changes now keeps its candidate identity and increments `sourceRevision`, matching the REV10 Target identity contract.
- Acquisition handoff IDs are session+candidate-bound and are released in `finally`, including failed validation/staging paths.
- Reconciliation errors are converted to terminal failed jobs and release leases instead of being swallowed and leaving stuck jobs.

## Phase 2 tests/checks added

- `tests/unit/processing-spec.test.ts`: canonical ProcessingSpec, deterministic fingerprint, WorkSignature invalidation.
- `tests/unit/delivery-gate.test.ts`: exact freshness plus stale document/sourceRevision rejection.
- `tests/unit/binary-store.test.ts` (uses `fake-indexeddb`): atomic stage+lease, owner isolation, pointer-loss recovery, abnormal IndexedDB connection-close/reopen recovery, independent delivery lease, stale-runtime/orphan cleanup with cache-lease preservation.
- `tests/phase2-offline-runner.mjs`: dependency-free SHA-256/spec/signature/freshness checks.
- `scripts/verify-phase2-contracts.mjs`: DB name/version/stores/indexes, 32 MiB guards, trusted message boundary, lease roles, sourceRevision increment, and no mock network endpoint.

## Checks completed in this environment

- `npm run check:structural`: passed for all source and unit-test TypeScript using the local TypeScript 5.8.3 compiler plus offline API stubs.
- `npm run check:offline`: passed: 15 inherited Phase 1 checks + 5 Phase 2 identity/delivery checks + Phase 2 contract verifier.
- `npm run check:phase2-contracts`: passed.
- `npm run check:fixture-manifest`: passed against the committed Phase 1 A–L fixture manifest.
- Static scan found no `TODO`, `FIXME`, `eval`, `new Function`, `innerHTML`, `outerHTML`, or `document.write` in project source/tests/scripts.
- Local runtime: Node v22.16.0; Chromium 144.0.7559.96.

## REV10 Phase 2 exit criteria

| Exit criterion | State |
|---|---|
| mock processing returns raster | Implementation and unit/browser path complete; real WXT + Chrome 148 execution remains blocked by environment |
| stale delivery tests pass | **Passed offline** for exact PageSession/document/sourceRevision gate; Vitest/browser version is also committed but awaits dependencies |
| SW kill reconciliation passes | Recovery implementation plus pointer-loss and abnormal-IDB-close tests are committed; actual Vitest execution and real Chrome worker termination gate are **not yet runnable here** |

Therefore the **Phase 2 source implementation is complete**, but the external release/exit gate is not claimed fully green until the real dependency tree and Chrome 148 test can run.

## External gate blocked in this container

A fresh registry probe fails with `EAI_AGAIN getaddrinfo registry.npmjs.org`. Consequently:

- `idb`, `fake-indexeddb`, WXT, Vitest, and project-local TypeScript cannot be installed here;
- a genuine `package-lock.json` cannot be generated or validated;
- `npm ci`, real WXT-aware `tsc`, Vitest BinaryStore tests, and WXT build cannot run;
- installed Chromium is 144, below the intentional Chrome 148 minimum.

REV10 requires a committed lockfile and `npm ci`. This artifact intentionally does not fabricate a lockfile. CI is configured to require it and then use `npm ci`.

On a machine with npm connectivity:

```bash
npm install --package-lock-only
npm ci
npm run check
npm run fixture
```

Then load `.output/chrome-mv3` in Chrome 148+ and perform the browser gate documented in `README.md`, including forced Service Worker termination between IDB staging and pointer checkpoint/reconciliation.

## Current dependency verification

Internet verification on 2026-08-19 confirmed `idb` 8.0.3 as the current package version used here and `fake-indexeddb` 6.2.5 as the current test package version. Chrome's current extension documentation states that IndexedDB is available to extension service workers for structured data including files/Blobs, and that `storage.session` is restricted to trusted contexts by default and cleared on browser restart.

## Intentionally out of scope until Phase 3+

No queue admission, priority bands, live Work dedupe, persistent translated-result cache behavior, cache promotion/GC/LRU, alarm wake, Local Processing Engine protocol, OCR, translation provider, inpainting, or Arabic rendering is activated in Phase 2.
