# Real production qualification execution — REV13

Audit/implementation date: 2026-08-19

## Scope

This closes the executable path from one sealed operator-input identity through registry-resolved dependency locks, a stable production benchmark run plan and, after a separate human benchmark review, to a lock-bound `production-profile-freeze.json`.

It does **not** claim that the source archive itself contains real production model bytes, an authorized corpus, human reviews, or a completed freeze. Those are operator-controlled inputs/evidence and must remain real.

## Why prepare and execute are separate

Artifact intake receipts contain acquisition-time provenance. Re-running acquisition/intake creates a different receipt set and therefore a different `runPlanSha256`. A benchmark review sealed for the first run plan must never be accepted for a newly generated one.

REV11 therefore uses two phases:

1. **prepare** — generate dependency locks on a network runner, acquire/intake artifacts once, and create one stable run plan;
2. **execute** — restore the exact locks and exact prepared workspace, require a review bound to that run-plan hash, execute the real corpus, evaluate the gate, and freeze only on pass.

## Phase 0 — seal and preflight operator inputs

Before prepare, create one `rev13-production-qualification-input-bundle-v1` with `seal_qualification_input_bundle.py`. It validates and hashes the authorized corpus manifest, all nine active artifact reviews, both reviewed LaMa/AOT runtime packages, and the active qualification control files. The protected workflow runs `probe_real_qualification_readiness.py --strict` against this same bundle before the hosted lock bootstrap can begin. See `docs/REV13_QUALIFICATION_INPUT_HANDOFF.md`.

## Phase 1 — prepare

Dispatch `.github/workflows/qualify-production-ml-self-hosted.yml` with `mode=prepare`, `input_bundle_relative` pointing to the sealed bundle, and `workspace_relative` selecting the protected output workspace.

The hosted `bootstrap-locks` job:

- uses Node 24.19.0 / npm 12.0.2 and Python 3.13.15 / uv 0.12.5;
- deletes any previous locks and performs registry-backed npm/uv resolution;
- validates the generated graphs with clean installs, tests and build checks;
- regenerates `SOURCE_SHA256SUMS.txt` with the generated lock bytes present;
- passes only the lock/control bundle to the protected self-hosted qualification job.

The protected self-hosted prepare job then:

- restores those exact lock bytes and verifies source integrity;
- re-verifies the single sealed REV13 input bundle below `MTE_QUALIFICATION_INPUT_ROOT`, rejecting traversal/symlink/hash/control-pin drift;
- validates the production corpus and rights chain **before network model acquisition**;
- requires final approved artifact reviews for every active artifact;
- opens and validates both reviewed manual-derived ONNX packages (`lama-big`, `aot-gan-places2`) before network model acquisition;
- asserts the active V1 topology is exactly seven automated primary-source artifacts plus those two manual-derived artifacts;
- acquires all seven automated artifacts from the allowlisted primary-source registry;
- independently records and verifies acquisition evidence, performs reviewed intake, and copies exact bytes/receipts into the protected workspace;
- creates `benchmark-run-plan.json` with exact corpus/policy/catalog/candidate/artifact/receipt/executor hashes **and exact `package-lock.json` + `engine/uv.lock` hashes**;
- seals the generated lock bytes, matching source-integrity manifest and source commit under `qualification-control/` inside the protected workspace.

Only safe metadata (`benchmark-run-plan.json` and `qualification-summary.json`) is uploaded from prepare. Model bytes, corpus pages, OCR traces and manual checkpoints stay on the self-hosted runner.

## Human review between phases

Use the run plan produced by prepare. Fill a copy of `engine/benchmark/benchmark-review.template.json` with actual human review results. Do not change the prepared workspace.

Seal the review against the exact ready run plan:

```bash
python engine/scripts/seal_benchmark_review.py \
  --draft /secure/reviews/benchmark-review.draft.json \
  --run-plan /secure/qualification/workspace/benchmark-run-plan.json \
  --output /secure/reviews/benchmark-review.sealed.json
```

`seal_benchmark_review.py` inserts/validates the exact `runPlanSha256` but does not invent review scores.

## Phase 2 — execute

Dispatch the same workflow with `mode=execute`, the same `corpus_relative` and `workspace_relative`, and `benchmark_review_relative` pointing to the sealed review.

Execute mode:

- refuses artifact-review/manual-artifact inputs, so it cannot silently re-intake different artifacts;
- requires the same source commit used by prepare;
- restores the exact generated dependency locks and matching source-integrity manifest from `qualification-control/`;
- validates that the current lock digests equal the run-plan lock pins before benchmark work starts;
- verifies the corpus, policy, catalog, candidate plan, executor source, every artifact, every receipt and the sealed human review against the stable run plan;
- runs the real schema-v2 benchmark and reconstructs the report from machine evidence;
- evaluates the production gate;
- writes `production-profile-freeze.json` **only when the gate passes**;
- removes/replaces any stale previous result set transactionally so a failed rerun cannot leave an old freeze looking current.

Raw benchmark evidence remains local. On a passing execution, only `production-profile-freeze.json` and the safe execution hash summary are uploaded.

## Freeze lock binding

REV11 changes the production run-plan revision to `rev11-production-benchmark-run-plan-v3` and the freeze revision to `production-profile-freeze-v4-source-and-release-evidence-bound` as of REV15. The v3 freeze keeps the lock binding and also carries candidate-plan identity plus role/SFX and selected-inpainting qualification evidence for final release derivation.

The freeze carries `dependencyLocks` containing:

- SHA-256 of the exact `package-lock.json`;
- SHA-256 of the exact `engine/uv.lock`;
- non-trivial graph package counts;
- the lock-pin policy revision.

Benchmark execution checks the current lock bytes before inference. Raw-evidence validation checks them again. The release-ready verifier also rejects a freeze whose lock pins differ from the current source locks.

## After the first passing freeze

The generated locks and freeze are evidence, not substitutes for source control. For the controlled V1 release, review and commit the **exact** generated `package-lock.json`, `engine/uv.lock`, matching `SOURCE_SHA256SUMS.txt`, and approved production freeze through the normal source/release process. Do not regenerate the lock graph during controlled promotion.

A real V1 freeze is not claimed until the execute phase has run on the authorized corpus and real reviewed artifacts and the gate has actually passed. REV13 changes the handoff/preflight layer, not this release criterion.
