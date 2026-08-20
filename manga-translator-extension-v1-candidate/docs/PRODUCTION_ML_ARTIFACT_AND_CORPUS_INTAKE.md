# Production ML artifact + corpus intake — REV10

This stage turns the production benchmark prerequisites into a fail-closed chain of custody. Source control still contains **no production model weights and no production corpus**.

## Decisions

- No runtime or benchmark script downloads weights automatically.
- Vendor benchmark numbers are discovery evidence only; V1 winners are selected only from the project corpus under `benchmark-thresholds-v3.json`.
- Candidate identity is fixed in `engine/benchmark/candidate-plan-v3.json`. Raw benchmark output may report metrics, but it may not choose a different artifact/family mapping.
- Every planned artifact needs a content-addressed provenance receipt bound to the exact local bytes and catalog revision.
- Derived LaMa/AOT ONNX packages additionally require the source-checkpoint SHA-256, converter revision/source, and exact MTE runtime contract in the receipt.
- Corpus rights review is page-bound and must include reviewer identity, review record, UTC timestamp, and evidence reference. `seal_corpus_manifest.py` computes file hashes; operators do not hand-type them.

## Artifact intake

1. Acquire bytes outside the Engine from the reviewed primary source. For automated Paddle/manga-ocr sources, use `acquire_official_artifact.py` with `acquisition-source-registry-v3.json`; the command emits a content-addressed acquisition record.
2. Copy `engine/model-catalog/artifact-review.template.json` to a secure review record and complete it. An approval is a human/legal/project decision; the tool does not infer one from a code license.
3. Dry-run intake:

```bash
python engine/scripts/intake_model_artifact.py \
  --catalog engine/model-catalog/model-candidates-v1.json \
  --artifact-id ARTIFACT_ID \
  --source /secure/incoming/FILE_OR_DIR \
  --review /secure/reviews/ARTIFACT_ID.json \
  --source-registry engine/model-catalog/acquisition-source-registry-v3.json \
  --acquisition-record /secure/acquisition/ARTIFACT_ID.acquisition.json \
  --artifacts-dir /secure/models \
  --receipts-dir /secure/model-receipts
```

4. After reviewing the printed digest/shape, repeat with `--commit`. This copies the exact bytes, updates the catalog pin/statuses, and writes `ARTIFACT_ID.receipt.json`.
5. Verify the full candidate set:

```bash
python engine/scripts/verify_artifact_receipts.py \
  --catalog engine/model-catalog/model-candidates-v1.json \
  --candidate-plan engine/benchmark/candidate-plan-v3.json \
  --policy engine/benchmark/policies/benchmark-thresholds-v3.json \
  --artifacts-dir /secure/models \
  --receipts-dir /secure/model-receipts
```

For a status report scoped to the active V1 plan (so blocked post-V1 research artifacts are not mislabeled as shipping blockers):

```bash
python engine/scripts/verify_model_catalog.py engine/model-catalog/model-candidates-v1.json \
  --candidate-plan engine/benchmark/candidate-plan-v3.json \
  --policy engine/benchmark/policies/benchmark-thresholds-v3.json
```

`engine/model-catalog/official-source-hints-v1.json` remains a historical discovery aid. The active machine-validated source identity is `acquisition-source-registry-v3.json`; even that registry is acquisition evidence only and never grants license/redistribution/benchmark approval.

## Corpus sealing

Start from `engine/benchmark/corpus/corpus-draft.template.json`. Each page needs reviewed benchmark-use rights plus `reviewRecordId`, `reviewedBy`, `reviewedAtUtc`, and `evidenceRef`. Images, annotations and optional clean references stay external.

```bash
python engine/scripts/seal_corpus_manifest.py \
  --draft /secure/corpus/corpus-draft.json \
  --corpus-root /secure/corpus \
  --output /secure/corpus/corpus-manifest.json
```

The sealer refuses parent traversal/symlinks and refuses a pre-existing digest that disagrees with the bytes. It then executes the normal production corpus gate.

## Freeze candidate identities before measuring

`engine/benchmark/candidate-plan-v3.json` fixes candidate ID, component, family and artifact IDs. Japanese has no primary/fallback role in v3: manga-ocr and PP-OCRv6 compete under the same CER/latency policy. The release gate compares the report candidate mapping to this plan exactly, not just by family coverage.

## Create a benchmark run plan

Only after the corpus, local artifacts and receipts exist:

```bash
python engine/scripts/prepare_benchmark_run.py \
  --corpus /secure/corpus/corpus-manifest.json \
  --policy engine/benchmark/policies/benchmark-thresholds-v3.json \
  --catalog engine/model-catalog/model-candidates-v1.json \
  --candidate-plan engine/benchmark/candidate-plan-v3.json \
  --artifacts-dir /secure/models \
  --receipts-dir /secure/model-receipts \
  --output /secure/results/benchmark-run-plan.json
```

A ready schema-v2 plan pins the corpus, policy, catalog, candidate plan, every artifact hash, every receipt hash, and the exact benchmark executor source digest. Do not hand-author a production raw benchmark record. Seal the real human-review record, then run `engine/scripts/execute_benchmark.py`; the executor re-hashes every planned input immediately before inference and emits schema-v2 machine evidence bound to that run plan. The final evaluate/freeze commands require the same plan and receipts. See `docs/PRODUCTION_BENCHMARK_EXECUTION_HARNESS.md`.

## Current fail-closed state

The repository is intentionally not preflight-ready. Real weights/corpus are absent; the V1 Paddle small/medium detector and recognizer candidates still need local hashes and review receipts, and LaMa/AOT need reviewed checkpoint + conversion receipts. The unresolved `comic-text-detector-model` is **not** a V1 blocker anymore: it is explicitly `benchmarkUseStatus: blocked` and excluded from `candidate-plan-v3` as post-V1 research until a reviewed pretrained artifact and runtime adapter exist. This avoids making V1 depend on an unaudited/unimplemented candidate without claiming that Paddle wins on vendor numbers.
