# Post-Phase9 V1 production runtime wiring

## Scope

Phase 9 itself was a release-hardening phase and intentionally froze the Phase 8 runtime. The REV10 V1 final audit then resumed runtime work to close production blockers. The historical Phase 8 tree hashes remain immutable; `release-control/runtime-baseline-v1-candidate.json` records the audited current V1-candidate runtime separately.

This step does **not** declare `default-v1` ready. It implements the production runtime paths without inventing corpus results, model hashes, checkpoint rights, provider credentials or browser/native smoke evidence.

## Implemented runtime paths

- `default-v1` is freeze-driven. The Engine never substitutes a different detector, OCR route, role revision or inpainter when the frozen winner is unavailable.
- PP-OCRv6 detection and PP-OCRv6 / Korean PP-OCRv5 recognition use explicitly local, hash-pinned model directories. Japanese `manga-ocr` likewise resolves only the frozen local artifact.
- Model archives are materialized through bounded, digest-addressed staging that rejects traversal, symlinks, hardlinks, device entries and unsafe archive expansion. Runtime adapters do not download missing model bytes.
- `visual-enclosure-sfx-guard-v1` is the production role gate. Explicit protected hints remain protected; otherwise only strong OCR plus fixed visual enclosure evidence may grant `translate-replace`. Lexical SFX cues can only remove permission, never grant it. Missing optional numeric support fails closed.
- Production inpainting uses `mte-onnx-inpaint-contract-v1`. The frozen LaMa/AOT winner must be supplied as a reviewed local ONNX package plus sidecar. The model output is composited only under the erase mask; protected source pixels are independently restored after typesetting and verified after exact lossless encode/decode.
- External translation is OCR-text-only, schema-constrained and explicit opt-in. Images, polygons, page URLs and visual context are not sent by the adapter. Exact block IDs must round-trip.
- `runtime-unavailable` distinguishes a valid freeze/assets set that the local binary cannot safely execute from missing downloads, renderer mismatch or provider misconfiguration.

## Benchmark binding added with Role/SFX hardening

The SFX safety gate is now evidence-driven rather than aggregate-driven:

1. raw benchmark input contains one `sfxRows` record for every independently annotated `sfx`/`uncertain` block;
2. the report builder recomputes translation exposure, erase/inpaint overlap, post-encode pixel changes, uncertain destructive edits, silent protected conflicts and protected-SFX recall from those rows;
3. release evaluation receives the raw file as a required input and deterministically rebuilds the normalized report;
4. the reported `pageId` + `blockId` + language set must exactly match the hashed corpus annotations;
5. the production role revision requires protected-SFX recall `1.0` and all destructive SFX rates/counts exactly zero.

A SFX block that remains `uncertain` is safe and counts as protected; the policy measures preservation permission, not semantic-label vanity accuracy.

## Inpainting artifact boundary

LaMa and AOT remain independent benchmark candidates. Their source repositories/checkpoints are not executed directly by the Engine. A candidate can enter `default-v1` only after a reviewed local conversion exposes the fixed MTE ONNX sidecar/tensor contract and the resulting package has exact SHA-256, provenance/license disposition and benchmark evidence. CPUExecutionProvider is the portable V1 baseline; hardware-specific acceleration requires a new frozen runtime revision rather than silent provider substitution.

## Still blocked before `default-v1 = ready`

The implementation exists, but release readiness remains false until all real evidence exists:

- legal production corpus and complete SFX/uncertain annotations;
- benchmark pass for the exact `visual-enclosure-sfx-guard-v1` revision with protected-SFX recall 1.0 and every destructive SFX metric exactly zero;
- reviewed, hash-pinned LaMa/AOT ONNX candidate packages and a benchmark-selected inpainting winner;
- reviewed checkpoint/artifact licensing and redistribution/provisioning state;
- production translation/provider/privacy tuple frozen with explicit consent where remote text transfer is used;
- locked production dependency graphs and installed runtime extras;
- final native artifacts plus fresh packaged-artifact smoke on every claimed platform/browser.

## Readiness semantics

For `default-v1`:

1. missing/invalid production freeze → `needs-download`;
2. missing/hash-mismatched selected artifacts → `needs-download`;
3. missing/mismatched Arabic renderer → `renderer-missing`;
4. unsupported/missing frozen runtime dependency or artifact contract → `runtime-unavailable`;
5. supported external text provider without explicit enablement/key → `misconfigured-provider`;
6. only after every gate above passes → `ready`.

The current repository intentionally remains before step 6 because the real corpus, model packages, benchmark freeze and release evidence are not present.
