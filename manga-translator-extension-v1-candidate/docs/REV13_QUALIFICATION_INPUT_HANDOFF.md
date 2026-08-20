# REV13 — Sealed real-qualification input handoff

Date: 2026-08-19

## Purpose

REV13 closes the remaining operator-handoff ambiguity before the first real production qualification run. Prepare no longer accepts an independently chosen corpus path, artifact-review directory and manual-artifact directory in the protected workflow. Those bytes must first be validated and bound into one `rev13-production-qualification-input-bundle-v1` manifest.

The bundle is **not** a legal or benchmark approval. It is a content-addressed binding of already reviewed operator evidence so the protected runner cannot accidentally qualify a different input set.

## Required operator input root

The paths may be named differently, but a typical protected root is:

```text
$MTE_QUALIFICATION_INPUT_ROOT/
  corpus/
    corpus-manifest.json
    pages/...
    annotations/...
    rights/...
  reviews/
    ppocrv6-small-det.review.json
    ppocrv6-medium-det.review.json
    ppocrv6-small-rec.review.json
    ppocrv6-medium-rec.review.json
    ppocrv5-korean-mobile-rec.review.json
    manga-ocr-base-0.1.16.review.json
    noto-sans-arabic-production-font.review.json
    lama-big.review.json
    aot-gan-places2.review.json
  manual/
    mte-lama-big-onnx-v1.zip
    mte-aot-gan-places2-onnx-v1.zip
  qualification-input-bundle.json
  workspace/                  # created by prepare
  benchmark-review.sealed.json # supplied only after prepare
```

The corpus manifest already binds every corpus page, annotation, rights-review record and source-registry revision. The REV13 bundle additionally pins the corpus manifest SHA-256, every active artifact-review SHA-256, both reviewed manual package SHA-256 values, the exact seven-automated + two-manual topology, and active catalog/source-registry/manual-policy/benchmark-policy/candidate-plan hashes.

## 1. Seal the exact prepare inputs

Run on the protected runner after the corpus, nine artifact reviews, and both LaMa/AOT packages are final:

```bash
python engine/scripts/seal_qualification_input_bundle.py \
  --root "$MTE_QUALIFICATION_INPUT_ROOT" \
  --corpus corpus/corpus-manifest.json \
  --reviews-dir reviews \
  --manual-artifacts-dir manual \
  --output qualification-input-bundle.json
```

The seal command fails unless:

- the schema-v2 corpus and every referenced byte/hash/rights record validate;
- the production corpus minimums pass;
- all nine active reviews are final for benchmark use/license and contain evidence;
- the manual set is exactly reviewed LaMa/AOT runtime packages with valid MTE ONNX contracts/derivation manifests;
- the active candidate topology is exactly seven automated artifacts plus LaMa/AOT.

Use `--replace` only after intentionally reviewing changed input bytes. A changed review, corpus manifest or manual package invalidates the old bundle.

## 2. Protected readiness gate

```bash
python engine/scripts/probe_real_qualification_readiness.py \
  --repo-root . \
  --input-root "$MTE_QUALIFICATION_INPUT_ROOT" \
  --input-bundle qualification-input-bundle.json \
  --output /secure/qualification/readiness.json \
  --strict
```

REV13 readiness requires the pinned Node/npm/Python/uv toolchain, TCP reachability to the required registry/model endpoints, and full semantic verification of the sealed bundle. The report remains diagnostic-only and cannot approve evidence or create a production freeze.

The GitHub `prepare` workflow now runs this same protected preflight **before** allowing the hosted dependency-lock bootstrap job to start.

## 3. Prepare the immutable qualification workspace

Workflow dispatch inputs for `mode=prepare` are now:

- `input_bundle_relative=qualification-input-bundle.json`
- `workspace_relative=workspace`

The workflow re-verifies the bundle again immediately before acquisition, then acquires exactly the seven automated artifacts, intakes those bytes plus reviewed LaMa/AOT, creates one stable run plan, and seals the exact dependency locks/source commit beside the prepared workspace.

For a direct protected-runner invocation using already materialized dependency locks:

```bash
python engine/scripts/prepare_qualification_from_bundle.py \
  --root "$MTE_QUALIFICATION_INPUT_ROOT" \
  --bundle qualification-input-bundle.json \
  --workspace workspace \
  --download-automated \
  --replace
```

`qualification-summary.json` records the sealed input bundle SHA-256. The formal benchmark run plan remains independently bound to the actual corpus, policies, catalog, candidate plan, acquired/manual artifact bytes, receipts, executor source and npm/uv lock hashes.

## 4. Human benchmark review

Do not modify the prepared workspace. Fill the benchmark-review draft from real results and seal it to the exact prepared `runPlanSha256`:

```bash
python engine/scripts/seal_benchmark_review.py \
  --draft "$MTE_QUALIFICATION_INPUT_ROOT/benchmark-review.draft.json" \
  --run-plan "$MTE_QUALIFICATION_INPUT_ROOT/workspace/benchmark-run-plan.json" \
  --output "$MTE_QUALIFICATION_INPUT_ROOT/benchmark-review.sealed.json"
```

## 5. Execute and freeze

Dispatch the same workflow with `mode=execute` and:

- `corpus_relative=corpus/corpus-manifest.json`
- `workspace_relative=workspace`
- `benchmark_review_relative=benchmark-review.sealed.json`

Execute does not consume the prepare review/manual inputs again. It restores the exact locks sealed by prepare, validates the stable run plan and sealed benchmark review, runs the real corpus benchmark, and writes `production-profile-freeze.json` only when the production gate passes.

## Current status

REV13 does not claim a production qualification pass. The source archive still contains no authorized production corpus, final human review set, reviewed LaMa/AOT package bytes, or real freeze. It makes the external handoff deterministic and fail-closed so the next protected run has one unambiguous input identity.
