# REV28 — Real Run Launch / Resume Automation

REV28 automates only the GitHub Actions stages in the first real V1 execution plan. It does **not** approve benchmark evidence, perform interactive Chrome acceptance, merge evidence pull requests, or synthesize any release evidence.

## Why this layer exists

REV27 could verify workflow run IDs after an operator launched them, but launch and resume were still manual. That left three avoidable operational risks:

1. an operator could dispatch the right workflow with the wrong stage inputs;
2. a local interruption after a successful dispatch could cause the same stage to be launched again;
3. a successful run ID could be recorded even though it was not the exact run launched for the current controller attempt.

REV28 closes those gaps with `scripts/first_real_run_controller.py`.

## Run-intent binding

Every production `workflow_dispatch` workflow now requires `run_intent_nonce`. The controller generates a random `mte-...` nonce, adds it to the workflow inputs, and every production workflow includes the nonce in `run-name`. Each job also requires a non-empty controller-style nonce in its authorization expression in addition to the existing default-branch and GitHub actor-ID checks.

The ledger records the nonce beside the verified run observations. A run is accepted only when all of the following agree:

- workflow path;
- workflow-dispatch event;
- current ledger source commit;
- default branch;
- authorized GitHub actor ID;
- successful conclusion;
- stage-specific mode marker where applicable;
- exact sealed run-intent nonce in the run display title.

## Crash-safe pending launch

Before dispatching anything, the controller writes a sealed `pendingLaunch` into the external first-run ledger. It contains the stage, source commit, nonce and resolved workflow inputs, but no token or secret values.

GitHub's current workflow-dispatch REST endpoint returns `workflow_run_id` directly. REV28 records that ID immediately. For compatibility, and for the narrow crash window between GitHub accepting a dispatch and the local process writing its response, resume can recover the run by the same workflow + source commit + run-intent nonce. It refuses ambiguous matches.

A failed workflow remains a failed pending launch. `retry-failed` is explicit: it archives the failed intent/run IDs in the operational ledger, creates a new nonce, and launches a new attempt. A failed run is never rewritten into a success record.

## Controller token

`MTE_PRODUCTION_CONTROLLER_TOKEN` is a **local operator credential**. It must not be stored in the repository or committed bootstrap JSON. The contract requires a fine-grained repository token with:

- Actions: write — dispatch workflows and read their runs;
- Contents: read — re-check the live default-branch commit before dispatch and before recording success.

PR merges remain an explicit boundary handled with the existing reviewed merge flow; the controller does not merge PRs.

## Commands

After the REV27/REV28 onboarding and ledger initialization:

```bash
python scripts/first_real_run_controller.py plan --ledger /secure/operator/v1-ledger.json
```

Launch or resume the next automated stage:

```bash
export MTE_PRODUCTION_CONTROLLER_TOKEN='...'
python scripts/first_real_run_controller.py advance --ledger /secure/operator/v1-ledger.json
```

Qualification prepare is the first stage requiring operator paths:

```bash
python scripts/first_real_run_controller.py advance \
  --ledger /secure/operator/v1-ledger.json \
  --input input_bundle_relative=sealed-input-bundle.json \
  --input workspace_relative=v1-qualification-workspace
```

After the manual benchmark-review record, execute reuses the successfully recorded prepare workspace automatically. The operator supplies only the corpus/review paths:

```bash
python scripts/first_real_run_controller.py advance \
  --ledger /secure/operator/v1-ledger.json \
  --input corpus_relative=sealed-corpus.json \
  --input benchmark_review_relative=benchmark-review.json
```

If the local controller is interrupted while a run is queued/running/waiting for environment approval, use the same command or `resume`; the sealed pending intent is reused. If a run completes unsuccessfully, inspect it first and only then use:

```bash
python scripts/first_real_run_controller.py retry-failed --ledger /secure/operator/v1-ledger.json
```

## Intentional stop points

The controller reports `blocked: true` instead of inventing completion for:

- benchmark review;
- merged evidence PR transitions;
- interactive Chrome 148/current-Stable acceptance;
- local release-evidence promotion;
- Store-installed Chrome acceptance;
- local public-evidence promotion.

Those boundaries are recorded with `first_real_run_handoff.py` after their real evidence/review exists. The next controller invocation then resumes from the new verified source commit.

## Evidence status

REV28 changes orchestration/provenance tooling only. It does not create dependency locks, production freeze, real native/browser smoke, Store evidence, or a release-ready capsule. V1 remains fail-closed until those external artifacts exist.

> REV30 permission update: normal orchestration now also needs `Pull requests:read` so the controller can bind qualification/evidence PR identities. Write access for evidence PR creation is intentionally separated into local-only `MTE_PRODUCTION_EVIDENCE_PR_TOKEN` (`Contents:write`, `Pull requests:write`). See `REV30_EVIDENCE_PR_CREATION_MERGE_HANDOFF.md`.
