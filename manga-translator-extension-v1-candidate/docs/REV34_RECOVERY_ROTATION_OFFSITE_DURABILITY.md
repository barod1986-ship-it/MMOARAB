# REV34 — Recovery rotation, independent copies and off-site durability

REV33 proves that one Recovery Bundle can rehydrate a fresh checkout after GitHub Actions artifact retention expires. REV34 addresses the next failure mode: **one surviving bundle is still one failure domain**.

## Policy

Operational recovery generations are managed by `scripts/first_real_run_recovery_rotation.py` and are deliberately separate from release evidence. A generation cannot become active unless all of the following are true:

1. the Recovery Bundle is valid and binds the exact current operational ledger;
2. at least two destinations with distinct `storageId` values and non-overlapping absolute roots contain byte-identical copies;
3. at least one destination is explicitly declared by the infrastructure operator as `offsite`;
4. every destination has a HMAC-SHA256 authenticated copy receipt;
5. the rotation state is HMAC-SHA256 authenticated with a local/offline key that is never written to the repository or Recovery Bundle; and
6. a copy from the off-site-declared destination is run through the real REV33 `restore` + `verify-restored` path against an exact checkout.

`offsiteDeclared` is infrastructure metadata supplied by the operator. The tool can prove storage identity/path separation and the exact bytes copied; software cannot prove physical geography or organizational independence of a mounted filesystem.

## Minimum retained generations

The default policy requires **two complete generations** to remain. `prune` is dry-run unless `--apply` is supplied. It refuses to remove anything unless the newest active generation covers the exact current ledger and has a passed real restore probe. With the default policy, generation 1 is not prunable until generation 3 is active and verified, leaving generations 2 and 3 intact.

Before deleting any copy, `prune` re-authenticates every receipt and re-hashes every bundle in the generation. It never deletes an active generation.

## HMAC key

Set `MTE_RECOVERY_ROTATION_HMAC_KEY` to a high-entropy value of at least 32 bytes and keep it outside GitHub repository/environment secrets and outside every Recovery Bundle. Store it in an operator password manager/HSM-backed secret store appropriate to the deployment. Losing this key does **not** make REV33 bundles unreadable, but it prevents authenticating the REV34 rotation state/receipts as trusted backup inventory.

## Operator flow

```bash
python scripts/first_real_run_recovery_rotation.py init-config \
  --release-id "$RELEASE_ID" \
  --output /secure/operator/recovery-rotation.json

python scripts/first_real_run_recovery_rotation.py set-destination \
  --config /secure/operator/recovery-rotation.json \
  --storage-id primary-vault --role primary \
  --root /mnt/primary-vault/mte

python scripts/first_real_run_recovery_rotation.py set-destination \
  --config /secure/operator/recovery-rotation.json \
  --storage-id offsite-vault --role offsite --offsite-declared \
  --root /mnt/offsite-vault/mte

python scripts/first_real_run_recovery.py export \
  --ledger release/first-real-run-ledger.json \
  --output /secure/operator/current-recovery.zip

python scripts/first_real_run_recovery_rotation.py rotate \
  --ledger release/first-real-run-ledger.json \
  --bundle /secure/operator/current-recovery.zip \
  --config /secure/operator/recovery-rotation.json \
  --state /secure/operator/recovery-rotation-state.json \
  --restore-checkout "$PWD"

python scripts/first_real_run_recovery_rotation.py verify \
  --ledger release/first-real-run-ledger.json \
  --config /secure/operator/recovery-rotation.json \
  --state /secure/operator/recovery-rotation-state.json
```

Run `rotate` immediately after every sealed ledger checkpoint. The release controller remains concerned with provenance/evidence ordering; external durability is operational infrastructure and does not itself satisfy a V1 release gate.

## Safe pruning

```bash
python scripts/first_real_run_recovery_rotation.py prune \
  --ledger release/first-real-run-ledger.json \
  --config /secure/operator/recovery-rotation.json \
  --state /secure/operator/recovery-rotation-state.json
```

Review the dry-run output first. Only then add `--apply`. The tool preserves at least two complete verified generations under the default policy.
