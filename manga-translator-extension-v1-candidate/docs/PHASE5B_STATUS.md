# Phase 5B Status — Production ML Benchmark & Model Pinning Gate — REV10

## Result

**Infrastructure complete; production benchmark intentionally not claimed as passed.**

Phase 5B implements the release gate required to finish the real Phase 5 exit without inventing model winners. The repository does not contain a copyrighted production corpus, production model weights, or a forged `production-profile-freeze.json`, so `default-v1` remains fail-closed.

## Implemented

- External legal corpus manifest with per-page image/annotation SHA-256.
- Reviewed benchmark-use rights are mandatory for every corpus page, including reviewer identity, review-record ID, UTC review time, and evidence reference.
- Corpus sealing computes file digests from reviewed drafts and refuses symlink/path escape or pre-existing hash conflicts.
- Corpus path containment, symlink refusal, raster format/frame/120MP bounds, annotation geometry bounds and duplicate-image rejection.
- REV10 coverage gate: English primary corpus, Japanese/Korean/Chinese fallbacks, visual edge cases, independent SFX pages and clean inpainting references.
- Language-specific detection, OCR, reading-order and translation-review sample gates.
- Raw benchmark normalization for detection/OCR/reading order/performance/Arabic rendering/human review, with per-block SFX/uncertain evidence rather than caller-supplied safety aggregates.
- Candidate identity is independently frozen in `candidate-plan-v3.json`; raw benchmark evidence cannot swap artifact IDs while keeping a family label. v3 also removes the previous Japanese primary/fallback exception: the frozen Japanese winner is selected by benchmark evidence.
- Versioned candidate comparison matrix in `benchmark-thresholds-v3`:
  - PP-OCRv6 small detector vs PP-OCRv6 medium detector;
  - PP-OCRv6 small vs medium for English;
  - manga-ocr primary vs PP-OCRv6 Japanese fallback;
  - Korean PP-OCRv5;
  - PP-OCRv6 small vs medium for Simplified/Traditional Chinese;
  - LaMa vs AOT.
- Deterministic winner selection; a report cannot hand-edit the winner.
- Separate code-license, benchmark-use, artifact-license and redistribution/provisioning states.
- Every **benchmarked** artifact, winner or loser, needs approved benchmark use plus a real matching local SHA-256 and content-addressed provenance receipt before the production gate can pass.
- Derived LaMa/AOT ONNX receipts bind the source-checkpoint SHA-256, converter source/revision and exact runtime contract.
- A benchmark run plan pins corpus, policy, catalog, candidate plan, every local artifact digest and every receipt digest before measurement begins; raw/report evidence must bind to that ready plan.
- The schema-v2 execution harness is source-pinned by that run plan, re-hashes every planned input immediately before inference, and is the only accepted production raw-evidence path.
- Detector candidate metrics are rebuilt from per-page trace counts rather than trusting duplicate aggregate fields; OCR metrics are rebuilt from exact per-block traces.
- Formal schema-v2 trace coverage is matched back to the authorized corpus: every detector covers every page, every OCR candidate covers exactly its eligible language blocks, inpainting covers exactly clean-reference pages, and reading-order/performance coverage cannot silently omit difficult pages.
- Local performance timing has an explicit scope: `local-ml-detector-ocr-role-inpaint-v1`. It uses detector-produced regions, not ground-truth crops. External translation latency and Arabic rendering are separate release evidence.
- Detector geometry scoring uses locally rasterized polygon pairs plus compact one-bit page unions so long webtoons do not allocate one full-page mask per predicted region. Binary-mask accounting counts every non-zero Pillow foreground representation, including ImageChops outputs.
- Inpainting human-review coverage/failures are taken from the deterministically selected winner, never summed across candidates.
- Selected production artifacts additionally require approved artifact-license/provisioning state.
- File or directory-tree artifact hashing; symlinks/path traversal refused.
- Noto Sans Arabic tracked as its own frozen renderer artifact.
- Exact runtime/hardware versions recorded in each report; no automatic “newest Paddle runtime wins” rule.
- NaN/Infinity rejected so non-finite values cannot bypass threshold comparisons or enter canonical hashes.
- Exact-zero SFX/uncertain destructive-edit gates remain non-tunable. Protected-SFX recall must be 1.0; all SFX metrics are recomputed from per-block raw rows whose page/block IDs must exactly match the independently hashed corpus annotations.
- Tamper-evident production freeze includes selected components, artifact pins, runtime, translation revision and renderer/font revision.
- `EngineProfileFingerprint` incorporates the approved freeze; exact local weights and configured font are rehashed before readiness.
- Production detector/OCR/role/translation/inpainting runtime paths are implemented separately from the benchmark gate; even after a valid freeze they remain fail-closed on missing runtime dependencies/artifacts/provider configuration. Fixture adapters never become production implicitly.

## Current unresolved production inputs

The committed candidate catalog is structurally valid but has no downloaded production weights or production provenance receipts. The active V1 candidate plan now benchmarks the official PP-OCRv6 small and medium detector artifacts against each other. Their exact bytes/hashes and review receipts are still absent, as are the remaining OCR/inpainting/font inputs. The unresolved comic-specialized detector is intentionally `blocked` and post-V1 research only; it no longer participates in the V1 run plan. This is a candidate-qualification decision, not a benchmark claim that Paddle is more accurate.

This is not a failed benchmark result. It means **the real benchmark has not been run yet** because the required legal corpus and audited local model artifacts are not present in this environment.

## Verification completed locally

- Python benchmark/Engine tests: 123/123.
- Phase 5 contracts: 22/22.
- Phase 5B contracts: 79/79.
- Phase 1 offline checks: 15/15.
- Phase 2 offline checks: 5/5.
- Phase 3 offline checks: 6/6.
- Inherited Phase 4 contracts: 42/42.
- Structural TypeScript: pass.
- Python compileall: pass.
- Phase 9 release-hardening contracts: 181/181 (REV15 evidence-closure audit).
- Source integrity: 356/356 tracked source files.
- Model catalog structural verification: pass and correctly reports production artifacts unresolved.

## Remaining real release gate

To close Gate D, run the included scripts on the external authorized corpus and locally acquired/audited candidate weights, record exact runtime/hardware, build the report, evaluate it, and only then generate `production-profile-freeze.json`.

Do **not** advance the production profile into Phase 6 as “ready” before that freeze exists and validates.

## Primary-source acquisition hardening

The active V1 chain now requires a source-registry identity before artifact intake. Automated Paddle/manga-ocr/Noto acquisitions emit a content-addressed acquisition record that is rebound into the provenance receipt; LaMa and AOT remain manual-derived and require independently reviewed checkpoint and converter provenance before deterministic ONNX packaging. `verify_acquisition_sources.py` checks the complete active v3 plan offline.
