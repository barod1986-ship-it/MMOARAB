# First Real Production Run Handoff — REV29

`first_real_run_handoff.py` is an **operator resume/provenance ledger**, not release evidence. Keep the generated ledger outside the tracked source tree. It is bound to the exact production-execution contract plus a sealed repository-onboarding configuration.

REV27 records three different facts explicitly instead of treating every step as the same kind of checkpoint:

- `record-run` verifies a successful `workflow_dispatch` run from the ledger's **current source commit**, on the bound default branch, from a sealed production **GitHub actor ID**, and from the expected workflow/mode.
- `record-pr-merge` verifies the reviewed PR really merged into the default branch, that its first parent is the ledger's current source commit, and that its changed paths stay inside the stage-specific allowlist. Only then does `currentSourceHeadSha` advance.
- `record-manual` records human boundaries only after a content-addressed checkpoint and the same evidence files are semantically revalidated; a boolean approval flag alone is rejected.
- `record` is reserved for local evidence-promotion preparation; it cannot impersonate automated or manual-checkpoint stages.

This matters because qualification evidence promotion creates a PR rather than mutating the release branch directly. Exact artifacts must be built from the **merged evidence commit**, not the pre-promotion qualification commit. The same rule applies to release-smoke evidence and, for `public-v1`, post-Store public evidence.

The release-class plans are different. `private-v1` can finalize after release-evidence merge. `public-v1` additionally requires `store-candidate → store-installed-chrome-smoke → public-evidence-local-promotion → public-evidence-pr-merged` before finalization.

Bootstrap/onboarding order:

```bash
python scripts/provision_github_production_infrastructure.py template --repository OWNER/REPO --output .mte-production-bootstrap.json
python scripts/provision_github_production_infrastructure.py set-runner --config .mte-production-bootstrap.json --role qualification-linux-x86_64 --name RUNNER_NAME
# Repeat set-runner for the other three roles.
python scripts/provision_github_production_infrastructure.py set-operator --config .mte-production-bootstrap.json --login OPERATOR_LOGIN
python scripts/provision_github_production_infrastructure.py bind --config .mte-production-bootstrap.json
```

Ledger initialization:

```bash
python scripts/first_real_run_handoff.py init \
  --output /secure/operator-state/mte-v1-first-run.json \
  --release-id v1.0.0-rc1 \
  --release-class private-v1 \
  --onboarding-config .mte-production-bootstrap.json

python scripts/first_real_run_handoff.py status \
  --ledger /secure/operator-state/mte-v1-first-run.json
```

For an automated stage, record the real Actions run ID:

```bash
python scripts/first_real_run_handoff.py record-run \
  --ledger /secure/operator-state/mte-v1-first-run.json \
  --stage qualification-prepare \
  --run-id 123456789
```

After a promotion PR is reviewed and merged, record the merge itself before continuing:

```bash
python scripts/first_real_run_handoff.py record-pr-merge \
  --ledger /secure/operator-state/mte-v1-first-run.json \
  --stage qualification-evidence-pr-merged \
  --pr-number 42
```

Manual review boundaries no longer accept `--manual-reviewed` by itself. Create them with `scripts/manual_boundary_checkpoint.py`, then use `record-manual` with the same evidence files so hashes and semantic bindings are revalidated and the authorized GitHub actor/default-branch cursor are checked again. Run IDs, PR numbers and manual checkpoints remain operational provenance pointers; the qualification, assembly, smoke, signing and final-capsule gates remain the authorities for release evidence.


## REV29 manual checkpoint example

```bash
python scripts/manual_boundary_checkpoint.py --stage benchmark-review \
  --ledger /secure/operator-state/mte-v1-first-run.json \
  --evidence run-plan=/secure/qualification/run-plan.json \
  --evidence benchmark-review=/secure/qualification/benchmark-review.json \
  --output /secure/operator-state/benchmark-review.checkpoint.json

python scripts/first_real_run_handoff.py record-manual \
  --ledger /secure/operator-state/mte-v1-first-run.json \
  --stage benchmark-review \
  --checkpoint /secure/operator-state/benchmark-review.checkpoint.json \
  --evidence run-plan=/secure/qualification/run-plan.json \
  --evidence benchmark-review=/secure/qualification/benchmark-review.json
```

The controller prints the required evidence roles whenever it reaches any of the three manual boundaries.
