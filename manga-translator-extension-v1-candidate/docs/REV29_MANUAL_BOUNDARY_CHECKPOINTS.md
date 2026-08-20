# REV29 — Manual Boundary Checkpoints

REV28 made automated first-run stages dispatch/resume-safe, but the three human boundaries were still weaker than the automated provenance chain: the operational ledger could record a boolean `manualReviewed` without binding the exact files that were reviewed.

REV29 replaces that boolean-only transition with a content-addressed manual checkpoint. The human decision is still intentionally human; the tooling only proves which bytes, repository identity, source commit and authorized GitHub operator were attached to that decision.

## Boundaries

The checkpoint is mandatory for:

1. `benchmark-review`
   - exact ready benchmark run plan;
   - exact sealed benchmark review;
   - verifies both content digests and exact `runPlanSha256` binding.
2. `chrome-148-and-stable-smoke`
   - exact controlled manifest;
   - exact `native-smoke-complete` orchestration session;
   - exactly two interactive unpacked-extension observations;
   - requires Chrome 148 and the Stable major frozen in `release-control/release-state.json` (151 in the 2026-08-20 audit).
3. `store-installed-chrome-smoke`
   - public controlled manifest;
   - `evidence-promoted` orchestration session;
   - Store submission handoff;
   - Store candidate metadata and the exact candidate ZIP bytes;
   - exactly two Store-installed observations for Chrome 148 and the audited Stable major.

## Two-step operator flow

Create the checkpoint only after the human review/interactive acceptance is complete:

```bash
python scripts/manual_boundary_checkpoint.py \
  --stage benchmark-review \
  --ledger /secure/operator-state/mte-v1-first-run.json \
  --evidence run-plan=/secure/qualification/run-plan.json \
  --evidence benchmark-review=/secure/qualification/benchmark-review.json \
  --output /secure/operator-state/benchmark-review.checkpoint.json
```

Then record it into the external first-run ledger using the **same evidence files**:

```bash
python scripts/first_real_run_handoff.py record-manual \
  --ledger /secure/operator-state/mte-v1-first-run.json \
  --stage benchmark-review \
  --checkpoint /secure/operator-state/benchmark-review.checkpoint.json \
  --evidence run-plan=/secure/qualification/run-plan.json \
  --evidence benchmark-review=/secure/qualification/benchmark-review.json
```

The second command re-runs semantic validation, re-hashes every evidence file and re-authenticates the GitHub operator. A checkpoint JSON with recomputed hashes but different evidence therefore cannot advance the ledger through the supported CLI.

## Identity checks

Checkpoint creation and recording both require the local `MTE_PRODUCTION_CONTROLLER_TOKEN` unless a test-only actor snapshot is explicitly supplied. The live checks require:

- authenticated GitHub actor ID is in the onboarding-sealed production operator allowlist;
- repository ID still matches the onboarding-bound repository ID;
- live default branch name still matches the bound default branch;
- live default-branch head still equals the ledger source cursor.

If the branch moves between checkpoint creation and recording, the checkpoint is stale and must be recreated/reviewed against the new cursor.

## Scope

A manual checkpoint is operational provenance, not release evidence. It does not replace the production freeze, browser observations, Store evidence, controlled manifest, smoke records or final release capsule. It also does not reduce any V1 release blocker merely by existing.
