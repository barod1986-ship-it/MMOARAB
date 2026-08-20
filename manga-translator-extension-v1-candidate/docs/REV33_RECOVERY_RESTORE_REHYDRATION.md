# REV33 — Recovery restore / rehydration closure

REV33 proves that the REV32 disaster-recovery archive is usable after the original GitHub Actions artifact storage and original runner workspace are gone. A recovery ZIP is no longer only exportable/verifiable; it can be restored into a fresh checkout at the exact sealed source cursor and used by the existing first-real-run controller.

## Restore boundary

Run the restore with the REV33 source checkout at the exact `currentSourceHeadSha` recorded by the bundle:

```bash
python scripts/first_real_run_recovery.py restore \
  --bundle /secure-independent-storage/<releaseId>-recovery.zip \
  --checkout /path/to/fresh/project-checkout
```

The restore requires a real Git checkout and fails closed unless all of the following agree with the sealed ledger/bundle:

- Git `HEAD` equals the recovery source cursor;
- the checked-out branch is the sealed default branch;
- `origin` resolves to the sealed `owner/repository` identity;
- the local production execution contract is byte-identical to the bundle witness;
- the complete production workflow-set hash matches the ledger;
- `SOURCE_SHA256SUMS.txt` is byte-identical to the bundle witness and the complete source-integrity verification passes.

The numeric GitHub repository ID is preserved in the ledger and restore manifest. It cannot be derived from an offline Git checkout; the first subsequent networked controller action rechecks that numeric ID through GitHub before it can dispatch anything.

## Atomic activation

REV33 does not restore individual files directly into several operational locations. It stages the complete recovery state and atomically renames one directory into:

`release/rehydrated/<releaseId>-<bundle-sha-prefix>/`

That directory contains:

- `ledger.json` — the original operational ledger semantics with only recovery-snapshot paths rewritten to the rehydrated root, then resealed;
- `recovery/<stage>/` — the exact content-addressed run/manual snapshots from the bundle;
- `manual/<stage>/` — convenience copies of already-reviewed checkpoint/manual input bytes;
- `artifact-catalog.json` — paths and SHA-256 identities for the exact preserved GitHub artifact ZIP bytes;
- `manual-catalog.json` — roles, names, hashes and paths for the restored manual inputs;
- `bundle-source-integrity/` — witness copies of the exact source checksum manifest and production execution contract;
- `RESTORE_MANIFEST.json` — content-addressed operational restore provenance.

No `git clean` is used and no source file is replaced by the restore operation. If the final content-addressed restore root already exists and verifies against the same bundle SHA-256, restore is idempotent.

## Restore provenance is not release evidence

`RESTORE_MANIFEST.json` records the original bundle SHA-256, bundle-manifest SHA-256, original ledger file SHA-256, rehydrated ledger SHA-256, repository/source/workflow bindings, last completed stage and next stage. This is operational provenance only. It cannot satisfy qualification, smoke, signing, Store, privacy or final release gates.

Verify the activated restore without the source bundle or GitHub artifact service:

```bash
python scripts/first_real_run_recovery.py verify-restored \
  --checkout /path/to/fresh/project-checkout \
  --restore-root /path/to/fresh/project-checkout/release/rehydrated/<restore-directory>
```

Then resume from the restored ledger:

```bash
python scripts/first_real_run_controller.py plan \
  --ledger release/rehydrated/<restore-directory>/ledger.json
```

`plan` is fully local and reopens every required restored recovery snapshot before reporting the next stage. A later `advance` still performs the normal live GitHub repository-ID/default-branch/actor/run checks before any new workflow can be dispatched.

## Regression proof

`tests/first-real-run-rehydration-smoke.py` creates a real temporary Git repository, produces a valid production-shaped recovery chain, exports the bundle, clones a fresh checkout that has none of the original operational recovery state, restores the bundle, deletes the bundle, and successfully runs the real controller `plan` command from the new checkout. The regression also proves fail-closed behavior for restored artifact tampering, origin substitution and source-HEAD drift.
