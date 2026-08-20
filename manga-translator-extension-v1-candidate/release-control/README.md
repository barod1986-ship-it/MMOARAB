# Controlled release evidence

This directory stores human-reviewed release state and evidence references. It deliberately contains no release binaries.

- `release-state.json` — current gate state; defaults fail closed. Flags are mirrors of evidence, not substitutes for evidence.
- `smoke-records.json` — fresh-environment smoke evidence. Valid records are bound to the SHA-256 of the exact `controlled-release.json`; V1 Engine records also identify the ready `default-v1` profile and the exact target-specific fingerprint; all three native targets must agree on privacy/provider semantics.
- `support-channels.json` — public support endpoints; empty until real.
- `production-downloads.json` — public Engine artifact URLs/hashes; empty until artifacts are frozen.
- `runtime-baseline-phase8.json` — byte-level runtime freeze used to enforce no feature changes in Phase 9.
- `rollback-runbook.md` — operational rollback procedure.

Generated immutable release archives live under `release/controlled/` and are not committed as source evidence. `scripts/verify_controlled_release_ready.py` re-hashes those bytes, compatibility metadata and `SHA256SUMS`; a JSON flag alone cannot satisfy the final gate.

REV17 evidence collection uses `smoke-controlled-release-engine.yml` for exact native archives, `scripts/record_exact_browser_smoke.py` for real Chrome GUI acceptance, and `scripts/promote_release_smoke_evidence.py` for atomic promotion. `store/release/profile-privacy.json` is derived from the three native observations; it is not hand-authored production evidence.

## REV19 public Store evidence boundary

For `public-v1`, `release-control/v1-orchestration.json` has two distinct promotion points. `evidence-promoted` is the immutable pre-Store checkpoint used to authorize the exact Store candidate. After the exact candidate is uploaded/staged and Store-installed smoke is recorded on Chrome 148 plus the audited Stable major, `promote_public_release_evidence.py` advances the tracked checkpoint to `public-evidence-promoted`. Only that second checkpoint may satisfy final public-V1 release readiness.

### REV30 first-real-run controller + manual/evidence-PR checkpoints

`scripts/first_real_run_controller.py` launches contract-declared automated GitHub Actions stages and verifies source-transition PRs. `MTE_PRODUCTION_CONTROLLER_TOKEN` is local-only and requires `Actions:write` + `Contents:read` + `Pull requests:read`; it is not a release/environment secret. Each launch is written as a sealed `pendingLaunch` before dispatch and bound to `run_intent_nonce`. Manual reviews remain explicit operator boundaries, but REV29 requires `manual_boundary_checkpoint.py` + `record-manual` with revalidated evidence bytes and live authorized-operator/source identity. Local evidence preparation is atomically paired with exact PR creation via `scripts/evidence_transition_pr.py` and the separate local-only `MTE_PRODUCTION_EVIDENCE_PR_TOKEN` (`Contents:write` + `Pull requests:write`). Human PR merge remains explicit; the ledger accepts only the previously recorded PR number/head SHA.

### REV31 post-merge local checkout cursor

Every evidence merge is followed by a controller-only local checkout reconciliation stage. `scripts/reconcile_first_real_run_checkout.py` refuses unrelated/staged changes, proves reviewed dirty files match the exact merge blobs, fast-forwards/resets only to the ledger merge commit, preserves operational untracked release material, and requires Source Integrity afterward. This prevents a stale operator checkout from contaminating later local evidence promotion.

### REV32 first-real-run recovery snapshots

The operational first-real-run ledger now references content-addressed recovery snapshots under `release/recovery/`. Automated snapshots preserve verified GitHub run metadata and exact uploaded artifact ZIP bytes before ledger advancement; manual snapshots preserve the exact already-reviewed checkpoint/evidence files. `scripts/first_real_run_recovery.py` can export/verify a portable offline recovery ZIP. Recovery snapshots are not committed release evidence and do not satisfy release gates.

### REV33 recovery rehydration

`first_real_run_recovery.py restore` activates a verified exported recovery bundle into one content-addressed `release/rehydrated/<releaseId>-<bundleHash>/` directory on a clean checkout at the exact sealed source commit. The restored `ledger.json` is resealed only because local recovery paths are rewritten; `RESTORE_MANIFEST.json` separately binds the original bundle/ledger hashes to the rehydrated operational state. `verify-restored` is offline and controller `plan` can use the restored ledger without GitHub artifact storage. This state remains operational and is never consumed as release evidence.
