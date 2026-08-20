# Phase 5 Status — REV10

## Result

The Phase 5 **staged processing architecture and safety/reference vertical slice are implemented**. The production model-quality Exit Gate remains intentionally open because the required real licensed comic corpus/model artifacts are not present in this execution environment and the registry/model download path is unavailable.

## Implemented

- Explicit adapter protocols for detector, reading order, OCR router, block-role classifier, translator, inpainter, and renderer.
- Stage progress contract: `decode → detect → order → ocr → translate → mask → inpaint → typeset → composite → encode`.
- Stable geometry/order-derived block IDs.
- OCR routing policy:
  - English: PP-OCRv6 small/medium benchmark slot.
  - Japanese: manga-ocr primary, PP-OCRv6 fallback challenger.
  - Korean: Korean PP-OCRv5 mobile recognition route.
  - Simplified/Traditional Chinese: PP-OCRv6 small/medium benchmark slot.
- OCR QA that cannot unlock destructive editing on weak evidence.
- Fail-closed role policy: only dialogue/narration are translatable; SFX/other/uncertain are protected.
- Page-batch translator with exact block-ID round trip validation.
- Protected-mask guard and destructive overlap rejection.
- Reference inpaint adapter for deterministic safety tests; production LaMa/AOT slot remains benchmark-gated.
- Arabic renderer using Pillow+libraqm with RTL/language shaping, measured wrapping, font-size search, and startup self-test.
- Protected source-pixel recomposite before encoding.
- Exact-lossless WebP → PNG rescue.
- Post-encode/decode comparison fixed to inspect **all RGBA channel extrema**, not `getbbox()` alone.
- Strict structured result manifest validation and durable transient storage until Engine job TTL/release.
- Production `default-v1` fail-closed readiness and opt-in development-only `fixture-v1`.
- Extension pairing/capability introspection now works even when the production profile is not ready; work submission still requires `ready`.

## Important correction found during implementation

The initial pixel-equality helper used `ImageChops.difference(...).getbbox()` on RGBA. This can be misleading when RGB changes while the alpha-difference channel remains zero. The final implementation checks the extrema of every channel, and the independent SFX benchmark assertion uses the same all-channel rule.

## Tests completed here

- Phase 1 offline checks: 15/15.
- Phase 2 identity/delivery checks: 5/5.
- Phase 3 queue/cache checks: 6/6.
- Inherited Phase 4 contract checks: 42/42.
- Phase 5 contract checks: 20/20.
- Python Engine protocol/security/staged-pipeline tests: 18/18.
- Structural TypeScript: pass.
- Python compileall: pass.
- Real local Uvicorn socket smoke: `GET /healthz` returned HTTP 204 on `127.0.0.1:17891`.
- Arabic RAQM renderer startup/mixed-direction test: pass on the available local Pillow/libraqm/font stack.
- Ground-truth SFX reference vertical slice: pass; translator input for annotated SFX = 0 and changed-pixel count in annotated SFX after final encode/decode = 0.
- Protected-region conflict test: pass/fails closed before destructive processing.
- Malicious translated-SFX manifest validation test: rejected.

## Production gate not claimed

The reference test adapters are deliberately not production OCR/translation models. A real Phase 5 Exit requires a licensed representative comic corpus and installed model artifacts so we can measure and pin:

1. PP-OCRv6 small detector vs PP-OCRv6 medium detector on the project corpus;
2. PP-OCRv6 small vs medium on English comics and Chinese manhua;
3. manga-ocr vs PP-OCRv6 fallback behavior on Japanese manga;
4. Korean PP-OCRv5 quality on manhwa;
5. role-classifier SFX recall separately from the preservation gate;
6. LaMa vs AOT quality/latency/VRAM by hardware profile;
7. Arabic translation naturalness and fitting metrics;
8. model code/weights/dataset provenance and redistribution license metadata.

No unbenchmarked model revision/hash is inserted into `default-v1`, so cache/work identity cannot pretend a production selection has been made.

## Environment gates

`package-lock.json` is still not fabricated. The npm/full WXT/Vitest/Chrome 148 browser gate must run in an environment with registry access and Chrome 148+. The actual ML model benchmark likewise needs model downloads/artifacts not available here.
