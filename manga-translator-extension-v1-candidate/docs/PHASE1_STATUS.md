# Phase 1 — Page & Image Acquisition Status

Implementation target: REV10 `02_PAGE_AND_IMAGES.md`, plus only the minimum Phase 0 foundation needed to run it.

## Implemented

- Chrome MV3 / WXT project skeleton, Side Panel entrypoint, runtime-only isolated content script, typed messaging, `PageSession`, session persistence, and trusted storage policy.
- Candidate discovery for `<img>`, `<picture>` via child `<img>`, `<canvas>`, and large iframe visual regions.
- `currentSrc → src → data-src/data-lazy-src/data-original/data-url` source resolution.
- Generic ranking with image area, natural size, semantic/UI penalties, URL hints, grouping, URL-family grouping, and DOM-order metadata.
- Initial scan, mutation observation, 1600 px near-viewport observation, image load/error reconciliation, 5-second safety rescan, and SPA URL rotation.
- Source-key behavior for recycled elements and reattachment when a framework replaces a DOM node with a new node for the same logical source.
- Page-context image fetch, loaded-image canvas snapshot, direct canvas snapshot, main-origin Service Worker fetch, exact-origin HTTPS permission path, and visible screenshot fallback.
- 32 MiB compressed-source guard, image magic/decode validation, aspect-ratio anti-placeholder heuristic, exact candidate URL checks, sender/session/document checks, and redirect-origin authority validation.
- `captureVisibleTab` active-tab/focus check, two-calls-per-second protection, fresh retry geometry, bitmap/CSS viewport scale calculation, VisualViewport offsets, and visible-intersection crop.
- Reversible image presentation, responsive `<picture>/srcset` preservation, same-source rewrite fallback to overlay, new-source invalidation, overlay presentation for canvas/screenshot/iframe, DOM-replacement reattachment, and Object URL cleanup.
- Stale acquisition protection: page-side cancellation plus a final background PageSession identity check before late results are stored/returned.
- Diagnostic Side Panel to inspect candidates, acquire/preview, grant an exact HTTPS image origin, choose screenshot fallback, show original, and restore all.
- Fixture server and basic CI workflow.
- Serialized `storage.session` mutations to avoid cross-tab read/modify/write races and stale-snapshot rollback.
- Phase 1 acquisition retention is bounded by both item count and a 128 MiB byte budget.

## REV10 A–L coverage

| Case | Fixture / implementation | Status |
|---|---|---|
| A same-origin `<img>` | `/same-origin` | Implemented |
| B `<picture>` + `srcset` | `/picture-srcset` | Implemented |
| C 100+ lazy Webtoon images | `/lazy` with 120 source-less lazy candidates | Implemented |
| D cross-origin CDN with CORS | `/cross-origin`, CORS endpoint on port 4174 | Implemented |
| E cross-origin CDN without CORS | permission policy + no-CORS fixture | Logic implemented; exact-origin grant must be browser-tested against HTTPS |
| F background fetch also fails | no-CORS/invalid remote paths → screenshot | Implemented fallback |
| G revoked Blob URL | `/revoked-blob` | Implemented fixture |
| H tainted canvas | `/tainted-canvas` | Implemented fixture |
| I SPA chapter change | `/spa` | Implemented |
| J virtualized same `<img>` changes source | `/virtualized` | Implemented |
| K DOM replacement, same sourceKey | `/replacement` + presentation reattach | Implemented |
| L cross-origin iframe reader | `/iframe` → viewport-region candidate → screenshot | Implemented |

## Checks completed in this environment

- `npm run check:structural`: full source + unit-test structural TypeScript check passed with the locally available TypeScript 5.8.3 compiler and offline API stubs.
- `npm run check:offline`: 15 dependency-free policy/math/source/scoring checks passed.
- `npm run check:fixture-manifest`: manifest contract verifier passed against the committed Phase 1 fixture manifest.
- Fixture HTTP servers started successfully; all fixture routes and CORS endpoint were requested successfully.
- Node available locally: v22.16.0.

## Browser/build gate not runnable in this container

The container cannot resolve `registry.npmjs.org` (`EAI_AGAIN`), so dependencies cannot be installed and the real WXT/Vitest build cannot be executed here. A final `npm install --no-audit --no-fund` retry on 2026-08-18 failed for the same DNS reason. Because no successful dependency resolution was possible, this source delivery intentionally does not fabricate a `package-lock.json`; create and commit it on the first successful online install before a release build. The installed Chromium is 144, while the extension intentionally declares Chrome 148 as its minimum. Therefore these commands remain the authoritative online/browser gate on a normal development machine:

```bash
npm install
npm run check
npm run fixture
```

Then load `.output/chrome-mv3` in Chrome 148+ and exercise the fixture matrix above. This is an environment limitation, not a substituted claim that the real WXT build already passed.

## Intentionally out of scope

No OCR, translation, SFX classification, inpainting, Processing Engine, durable BinaryStore, queue/cache, or production UI is included in Phase 1.
