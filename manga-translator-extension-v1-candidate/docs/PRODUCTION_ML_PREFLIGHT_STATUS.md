# Production ML Preflight Status — REV10 V1

## Active immutable inputs

- Policy: `engine/benchmark/policies/benchmark-thresholds-v3.json`
- Candidate plan: `engine/benchmark/candidate-plan-v3.json`
- Catalog: `engine/model-catalog/model-candidates-v1.json` revision `production-model-candidates-2026-08-19-v3`
- Corpus policy: `rev10-production-corpus-v2`
- Corpus source registry: `production-corpus-sources-2026-08-19-v1`
- Role/SFX revision: `visual-enclosure-sfx-guard-v1`
- Inpaint runtime contract: `mte-onnx-inpaint-contract-v1`

The superseded v1 detector policy/plan are retained as historical evidence and are not the active V1 release gate.

## V1 detector decision

V1 benchmarks `PP-OCRv6_small_det` against `PP-OCRv6_medium_det` on the same reviewed project corpus. `comic-text-detector-model` is kept in the catalog as post-V1 research with `benchmarkUseStatus: blocked`; it is excluded from the active V1 candidate plan. This is a release-qualification decision, not an accuracy claim.

## Planned V1 artifacts still requiring real local evidence

1. `ppocrv6-small-det`
2. `ppocrv6-medium-det`
3. `ppocrv6-small-rec`
4. `ppocrv6-medium-rec`
5. `ppocrv5-korean-mobile-rec`
6. `manga-ocr-base-0.1.16`
7. `lama-big`
8. `aot-gan-places2`
9. `noto-sans-arabic-production-font`

No production corpus, model weights, provenance receipts, ready benchmark run plan, benchmark result, or `production-profile-freeze.json` is committed by this stage.

## Required order

1. Complete the content-addressed corpus rights chain, then seal the schema-v2 external corpus manifest. Public availability or a boolean authorization field alone is insufficient.
2. Acquire each planned artifact from a reviewed primary source outside the runtime path.
3. Complete the review record, intake exact bytes, and create content-addressed receipts.
4. Convert reviewed LaMa/AOT source checkpoints into the fixed MTE ONNX wrapper contract and record source/converter provenance.
5. Run `verify_artifact_receipts.py` and the candidate-plan-scoped catalog verifier.
6. Create a ready content-addressed benchmark run plan.
7. Execute measurements on the same corpus/hardware policy, build the deterministic report, evaluate the gate, and freeze only if every quality and exact-zero SFX gate passes.

Nothing in this stage authorizes fabricating hashes, rights decisions, human-review scores, or browser/release evidence.

## Primary-source acquisition status

Primary-source identities and acquisition mechanics are now separately versioned in `engine/model-catalog/acquisition-source-registry-v3.json`; see `PRODUCTION_ML_PRIMARY_SOURCE_ACQUISITION.md`. Seven V1 artifacts have automated, allowlisted acquisition paths; LaMa and AOT remain manual-derived while the Arabic font is pinned to the reviewed Noto Sans Arabic 2.013 release ZIP member. No missing production bytes/hashes are claimed in this repository.


## Corpus rights qualification status

Production corpus admission is now independently source-registered and content-addressed. Operator-owned/explicitly permissioned pages may qualify only with page-scoped reviewed evidence. Manga109-s is a conditional Japanese source only after operator access/current-terms review is recorded. OpenMantra is excluded from the default production/commercial V1 qualification path because its public dataset license is noncommercial; separate permission would need to be represented as a different operator-rights record. Synthetic/self-authored pages are supplemental only and cannot satisfy real-domain minimums. See `PRODUCTION_CORPUS_RIGHTS_CHAIN.md`.
