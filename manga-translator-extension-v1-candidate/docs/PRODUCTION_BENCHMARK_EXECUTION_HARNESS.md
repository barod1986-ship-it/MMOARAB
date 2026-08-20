# Production benchmark execution harness — REV10

## Purpose

The formal V1 benchmark no longer accepts a hand-authored raw benchmark file as release evidence. `prepare_benchmark_run.py` creates schema-v2 run plans that pin not only corpus/policy/catalog/candidate/artifact/receipt digests, but also the exact benchmark executor revision and a SHA-256 over every source file that can change inference or metric semantics.

The formal executor is `engine/scripts/execute_benchmark.py`. It revalidates and re-hashes all run-plan inputs immediately before inference. If the corpus manifest/files, policy, catalog, candidate plan, any model bytes, any provenance receipt, or the executor source bundle changed after planning, execution stops.

## Executor source pin

`mte_engine.benchmark.execution.executor_source_digest()` hashes the path and bytes of the executor plus detector, OCR, reading-order, role/SFX, inpainting, metric and selection code. A ready run plan records:

```json
{
  "executor": {
    "revision": "rev10-production-benchmark-executor-v1",
    "sourceSha256": "sha256:..."
  }
}
```

Evaluating schema-v2 raw evidence on a different executor tree is rejected. Historical evidence therefore needs the source checkout that produced its run plan.

## Human review is separate evidence

Human judgments are not invented by the runner. Start from `engine/benchmark/benchmark-review.template.json`, complete the real inpainting/translation/renderer review, bind it to the ready `runPlanSha256`, then seal it:

```bash
python engine/scripts/seal_benchmark_review.py \
  --draft /secure/results/benchmark-review.draft.json \
  --output /secure/results/benchmark-review.json
```

The sealer only content-addresses the supplied review. It does not approve a candidate, infer a score, or change values.

## Formal execution

```bash
python engine/scripts/execute_benchmark.py \
  --run-plan /secure/results/benchmark-run-plan.json \
  --corpus /secure/corpus/corpus-manifest.json \
  --policy engine/benchmark/policies/benchmark-thresholds-v3.json \
  --catalog engine/model-catalog/model-candidates-v1.json \
  --candidate-plan engine/benchmark/candidate-plan-v3.json \
  --artifacts-dir /secure/models \
  --receipts-dir /secure/model-receipts \
  --review /secure/results/benchmark-review.json \
  --output /secure/results/raw-benchmark-v2.json
```

Production inference uses the same local freeze-compatible adapters as the Engine. No model download is permitted. Model archives are materialized through the same traversal/symlink/link/device/size guards as production runtime.

## What schema-v2 records

The raw record contains `execution.machineEvidence`, including per-candidate detector **per-page** counts/timings, per-block OCR reference/prediction evidence with measured timings, inpainting clean-reference measurements, reading-order rows, SFX/uncertain safety rows, page timing, and measured process peak RSS. It also embeds the sealed review snapshot and exact runtime package/OS/CPU metadata.

`evidenceSha256` covers the complete schema-v2 record (excluding the digest field itself). It detects accidental/post-run editing; it is not a hardware-backed signature and should not be represented as proof against a malicious operator with full local source access.

## Independent reconstruction

`build_benchmark_report.py` treats schema-v1 raw files as historical/fixture input only. For schema v2 it ignores caller-provided aggregate candidate metrics and reconstructs them from `machineEvidence`:

- detector recall/precision/F1/safety counts are rebuilt by summing unique per-page detector traces; duplicate aggregate fields are ignored;
- OCR CER and timings are rebuilt from per-block rows;
- inpainting human scores come only from the embedded sealed review record while machine timings/clean-reference values come from executor traces;
- winner selection is rerun from the versioned policy;
- selected detector/OCR/inpainting quality, SFX rows, reading order and performance are projected from execution evidence rather than duplicate top-level aggregates.

When a ready run plan is supplied, `evaluate_benchmark.py` requires valid schema-v2 executor evidence. A schema-v1/manual raw file cannot satisfy the production gate.

## Coverage binding and performance semantics

For schema v2, the release gate cross-checks machine traces against the sealed corpus rather than only counting samples. Every detector candidate must contain exactly one page trace per corpus page. Each OCR candidate must contain exactly the dialogue/narration block IDs eligible for its language component. Each inpainting candidate must cover exactly the corpus pages with clean references. Reading-order evidence must cover exactly the pages whose text blocks have complete reading-order ground truth, and `pageSeconds` must contain one measurement per corpus page.

`pageSeconds` is deliberately scoped to `local-ml-detector-ocr-role-inpaint-v1`: selected detector inference, OCR on detected regions, conservative role classification, and selected local inpainting. It does **not** include an external translation-provider network round trip or Arabic rendering; those are evaluated by their separate review/golden/runtime contracts. The scope value is release-gated so a different timing definition cannot be substituted silently.

Long webtoon pages are handled with compact mode-1 union masks and locally rasterized polygon-pair IoU. The benchmark does not allocate a full-page raster mask for every detector prediction. Pixel counts treat every non-zero mode-1 histogram bin as foreground because Pillow direct drawing and `ImageChops` logical operations can use different non-zero representations.

Human inpainting coverage in the final report is the review coverage of the **selected inpainting winner**, not a sum across all candidates.

## Security boundary

This design provides strong reproducibility, traceability and fail-closed checks against stale/mixed/tampered files. It cannot cryptographically prove that a person with arbitrary local code execution actually ran ML inference rather than fabricating a complete trace and recomputing hashes. Achieving that stronger property would require an external trusted signing/attestation service or hardware-backed execution environment and is outside V1's local benchmark threat model.
