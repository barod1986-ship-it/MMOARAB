# REV32 — Artifact retention and disaster recovery

REV32 removes a hidden dependency on the lifetime of GitHub Actions artifacts. A successful workflow run is not committed to the first-real-run ledger until its run metadata and every uploaded Actions artifact have been copied into a local content-addressed recovery snapshot under `release/recovery/<releaseId>/stages/<stage>/`.

## Automated stages

`scripts/first_real_run_recovery.py` enumerates the artifacts for every verified run ID, records each artifact's GitHub ID/name/size/creation and `expires_at` values, downloads the exact ZIP archive immediately, validates the GitHub SHA-256 digest when the API exposes it, and seals all local files in `recovery-manifest.json`. The authenticated GitHub request is used only to obtain the artifact redirect; the short-lived signed redirect target is fetched without forwarding the GitHub Authorization header.

Critical stages also declare a minimum artifact count in `production-execution-contract.json`. If an expected artifact has already expired, is missing, has an invalid digest, or cannot be archived, the successful workflow run remains uncommitted in `pendingLaunch` rather than silently advancing the ledger.

## Manual boundaries

`record-manual` now archives the already-reviewed checkpoint plus the exact evidence files that were revalidated at recording time. This preserves the reviewed bytes without turning the recovery copy into new qualification/smoke/Store evidence.

## Continuation and export

Before every controller continuation, all prior recovery snapshots are re-opened and every listed SHA-256/size is checked. Missing or modified recovery material blocks continuation.

A portable bundle can be exported and verified offline:

```bash
python scripts/first_real_run_recovery.py export \
  --ledger release/first-real-run-ledger.json \
  --output release/recovery/v1.0.0-rc1-recovery.zip

python scripts/first_real_run_recovery.py verify-bundle \
  --bundle release/recovery/v1.0.0-rc1-recovery.zip
```

The bundle includes the operational ledger, production execution contract, Source Integrity manifest, and all recovery snapshots referenced directly by the ledger. It remains operational disaster-recovery material, not release evidence.

## Retention policy

REV32 deliberately does not treat a longer GitHub retention setting as a recovery mechanism. GitHub artifacts can expire according to repository/organization/enterprise policy and are also removed if their workflow run is deleted. Recovery therefore happens immediately after each verified successful run while the artifact still exists.
