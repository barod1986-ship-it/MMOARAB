# Phase 6 status — UI productionization

## Scope implemented

Phase 6 is implemented on top of the Phase 5B benchmark gate. It intentionally does **not** mark `default-v1` ready while the legal production corpus/model freeze is absent.

### Side Panel

- React + TypeScript primary daily UI; no default popup.
- Trusted action/keyboard activation remains the `activeTab` gateway; `sidePanel.open({tabId})` is called before asynchronous activation work.
- Page states: unsupported, inactive, activating, ready, stale/error.
- Source/profile selectors derived from capabilities; Arabic target is fixed.
- SFX policy is read-only `preserve-original`.
- Translate page / per-candidate controls with exact-origin permission request from a direct user click and screenshot fallback where permitted.
- Real queue/engine stage and progress; indeterminate UI is used when no real numeric progress exists.
- Cancel only; no fake pause.
- Grouped blocking/item/session errors with setup/recheck/retry actions.
- Candidate list now persists and shows detector presentation state (`detected`, `waiting-load`, `ready`, `permission-needed`, `acquired`, `translated`, `stale`).
- Restore-originals control.
- Optional compact extension-owned Shadow DOM original/translation toggle.
- Auto-show off retains a terminal `ready-result` instead of discarding or forcing presentation.

### Options

Sections implemented: General, Translation, Local Engine, Provider, Appearance, Keyboard & Controls, Storage & Cache, Diagnostics, About.

Local Engine setup is deliberately centralized here:

1. request the literal `http://127.0.0.1/*` optional host permission;
2. direct `/healthz` probe from the extension page;
3. LNA diagnosis using `loopback-network` with `local-network-access` query fallback;
4. masked pairing token and pair/disconnect;
5. capability/profile readiness and production-gate status.

The UI distinguishes “Engine connected” from “selected profile ready”. Privacy text is derived from the capability `privacy` descriptor rather than guessed from provider/profile names.

### Settings and trusted boundaries

- UI locale: system / English / Arabic.
- source language: configurable from supported capabilities; target is always Arabic.
- theme: system / light / dark.
- result auto-show and compact page controls are functional, not cosmetic.
- cache enabled + 128/256/512 MiB maximum + approximate usage + clear.
- UI messages that read/change privileged state require trusted extension-page senders.
- `ProcessingSpec` is constructed inside Background state; UI cannot supply arbitrary destructive/SFX semantics.
- pairing tokens do not enter content-script messages or diagnostics.
- diagnostics omit page URL, manga title, OCR/translation text, pairing/provider secrets, filesystem paths, and image contents.
- no external telemetry endpoint is introduced.

### i18n and accessibility

- complete application/Chrome catalogs for English and Arabic;
- structural Chrome locale catalogs for Japanese, Korean, Simplified Chinese, and Traditional Chinese;
- bidi-aware document language/direction;
- keyboard-focus styles, accessible button labels/live regions, and reduced-motion handling;
- one Side Panel polling controller: ~1 s while work is active, ~2.5 s when idle.

## Verification completed in this environment

- strict structural TypeScript check: **PASS**;
- inherited Phase 1 offline checks: **15/15**;
- Phase 2 identity/delivery checks: **5/5**;
- Phase 3 queue/cache checks: **6/6**;
- Phase 4 contracts: **42/42**;
- Phase 5 contracts: **20/20**;
- Phase 5B benchmark-gate contracts: **33/33**;
- Phase 6 UI contracts: **30/30**;
- Python Engine tests: **39/39**;
- Python `compileall`: **PASS**.

That is **151** JS/contract/offline checks plus **39** Python tests, in addition to structural TypeScript and Python compilation.

## Release gates not claimed complete

1. **Real npm/WXT/Vitest build:** npm registry access from this execution environment still times out, so no truthful `package-lock.json` could be generated and `npm ci`/real WXT build/Vitest were not run here. CI deliberately refuses to proceed without a committed real lockfile.
2. **Chrome 148 acceptance:** local Chromium is `144.0.7559.96`; therefore Chrome 148-specific Structured Clone/LNA/full MV3 browser acceptance remains external.
3. **Production ML Gate D:** `default-v1` remains non-ready until the Phase 5B legal corpus/model benchmark, artifact hashes/licenses, and production profile freeze pass. Phase 6 surfaces this as a blocker.
4. **Non-developer end-to-end acceptance:** source/UI paths and `fixture-v1` support are implemented, but a real Chrome 148 + installed npm build + companion installation must be used for the final clean-machine acceptance test.

No release claim should override any of the four gates above.
