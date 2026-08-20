# Phase 4 Status — REV10

## Result

Source implementation for Phase 4 is complete: the extension now talks to a real loopback Python Engine protocol shell instead of the Phase 3 mock gateway.

## Implemented

- Fixed `127.0.0.1:17891` loopback endpoint and optional extension host permission.
- Side Panel setup/probe path for Local Network Access before background reliance on loopback.
- Opaque local bearer token, exact-extension-origin pairing, reset/token rotation, strict CORS.
- FastAPI/Pydantic/Uvicorn Engine shell with production docs disabled and proxy headers disabled.
- SQLite durable jobs plus filesystem source/result spool.
- Idempotent job create, raw-byte upload, start/restart, status, cancel, result, manifest, release.
- Startup conversion of in-flight Engine states to `interrupted`, then same-ticket restart.
- Deterministic source/result spool names derived only from server-issued tickets.
- Source SHA-256/size/MIME checks and 32 MiB source/result caps.
- 120 MP decoded-pixel guard.
- Deterministic exact-lossless image fixture: WebP lossless then PNG rescue; pixel verification after encode/decode.
- Extension-side bounded result streaming and post-download integrity/profile/dimension validation.
- Durable WorkRecord `engineTicket` and idempotent recovery across MV3 worker death.
- Engine `profile_changed` handling that recomputes WorkSignature/cache identity and migrates consumers.
- Existing Phase 3 shared `queue-wake` alarm reused for durable Engine rechecks.

## Corrections made during Phase 4

1. Fixed a duplicated-result-field SQLite success UPDATE that would have broken the first successful completion.
2. Changed strict Pydantic `translatableKinds` from tuple input semantics to JSON-list semantics while retaining exact-value validation.
3. Preserved CORS on pairing-reset responses even though reset clears the paired origin before the response is returned.
4. Replaced random final spool filenames with ticket-derived final paths to avoid crash-window orphans.
5. Replaced unbounded `response.blob()` result ingestion with bounded streaming before Blob construction.
6. Persisted Engine failure retryability in SQLite so restart/status does not lose retry semantics.
7. Added profile-fingerprint migration so a changed Engine profile cannot reuse an obsolete WorkSignature/cache key.
8. Fixed Side Panel handling so durable `waiting-work`/`joined-work` states are shown as queued rather than false errors.
9. Updated FastAPI pin to `0.141.1` after final release-note verification.
10. Rejected any Engine port other than `17891`, matching the extension's fixed endpoint and REV10 contract.
11. Revalidate an already-staged source by size and SHA-256 before idempotent reuse; a corrupted spool file is removed and may be re-uploaded safely.
12. Added explicit CORS preflight tests for initial pairing, paired origin, and rejection of a different extension origin.
13. Upgraded CI from Phase 3 to Phase 4 with separate extension and Python 3.11/3.13 Engine gates.
14. Authentication moved into middleware for sensitive `/v1/*` routes so unauthenticated JSON is rejected before FastAPI/Pydantic body parsing.
15. Hardened local privacy with user-only directory/file modes (`0700`/`0600`) where the OS supports POSIX permissions.
16. Added concrete WebP/zlib/JPEG/libjpeg-turbo/AVIF runtime versions to the Engine profile fingerprint so cache identity changes when raster codec semantics may change.

## Tests completed in this environment

- Phase 1 offline checks: 15/15.
- Phase 2 identity/delivery checks: 5/5.
- Phase 3 queue/cache checks: 6/6.
- Phase 4 static/protocol contract checks: 42/42.
- Python Engine protocol/security tests: 10/10.
- Structural TypeScript: pass.
- Fixture-manifest contract: pass.
- Python compileall: pass.
- Real local Uvicorn socket smoke test: `GET /healthz` returned HTTP 204 on `127.0.0.1:17891`.

The Engine test suite covers pairing/origin/Host checks, strict schema/no-URL input, idempotency, raw upload/hash validation, exact-lossless result integrity, cancellation/reset, Engine restart interruption/restart, fixed bind contract, profile-change recovery, and static no-outbound-fetch/no-unsafe-deserialization checks.

## Environment gates not claimed as passed

The local Python environment has older FastAPI/Uvicorn than the pins. An isolated exact-pin installation was attempted but failed because this environment could not resolve the package registry. The test suite nevertheless passes against the installed compatible runtime, while exact-pin installation remains a release-environment gate.

The npm registry is likewise unavailable from this execution environment, so there is no fabricated `package-lock.json` and no claimed WXT/Vitest build. The installed browser is Chromium 144, below the project baseline Chrome 148, so a real Chrome 148 Local Network Access prompt plus forced MV3 Service Worker death/revival browser test remains an external release gate.

## Phase boundary

No OCR/translation/inpainting/rendering ML is introduced here. Phase 5 is the staged processing pipeline.
