# Production Role/SFX + Inpainting Gate

## Goal

V1 translates dialogue/narration while preserving sound effects and any uncertain text. Destructive editing permission is intentionally harder to obtain than text detection/OCR acceptance.

## Role/SFX policy

Production revision: `visual-enclosure-sfx-guard-v1`.

The gate first honors explicit protected hints (`sfx`, `other`, `uncertain`). Without a semantic hint it requires strong OCR plus local visual evidence of a quiet speech/narration container and a surrounding boundary. Broad lexical SFX guards can only convert a candidate into `preserve-original`; they can never grant editing. Text that does not clear every grant condition is `uncertain` and protected.

The benchmark release policy now requires the exact production role revision and **protected-SFX recall 1.0**, in addition to the existing exact-zero requirements for SFX sent to translation, erase/inpaint overlap, protected pixel changes, uncertain destructive edits, and silent protected conflicts. “Protected recall” is the relevant safety property: an SFX block may be labeled `sfx` or conservatively remain `uncertain`, but it must never receive destructive edit permission.

The metric is no longer trusted as an aggregate. `sfxRows` contains per-block evidence keyed by corpus `pageId` + annotation `blockId` + language. The report builder recomputes all SFX rates from those rows, and the release gate rebuilds the report from the raw file and requires exact coverage of the independently hashed corpus annotations. This is intentionally a safety floor rather than a claim that the heuristic is universally correct before the real corpus is run.

## Inpainting policy

Production uses `mte-onnx-inpaint-contract-v1` and local SHA-256-pinned candidate packages. LaMa and AOT remain benchmark candidates; neither is selected by source-code preference. Their upstream runtimes are not imported into the Engine. A reviewed conversion must expose the fixed MTE ONNX tensor contract described in `engine/benchmark/INPAINT_ONNX_CONTRACT.md`.

ONNX output is composited only beneath the erase mask, so a model cannot modify unrelated source pixels. Protected SFX/uncertain pixels are independently excluded from the erase mask, recomposited from source after typesetting, and checked after exact lossless encode/decode.

## Still required before `default-v1 = ready`

- real annotated corpus with independent SFX labels;
- exact 1.0 protected-SFX recall for the frozen role revision and zero destructive SFX counters, derived from complete per-block raw evidence;
- locally converted/pinned LaMa and AOT packages with reviewed checkpoint provenance/licenses;
- hardware benchmark to select the inpainting winner;
- production freeze containing exact hashes and runtime versions;
- installed locked production dependencies, including ONNX Runtime;
- fresh packaged-artifact smoke on the claimed platforms.
