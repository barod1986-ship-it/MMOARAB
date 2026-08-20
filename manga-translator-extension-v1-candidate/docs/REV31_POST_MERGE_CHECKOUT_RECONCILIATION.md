# REV31 — Post-Merge Checkout Reconciliation

REV30 bound every evidence merge to the exact reviewed PR number/head SHA and advanced the operational source cursor only when the merge commit was the live default-branch HEAD. One local-state gap remained: the operator checkout could still be on the pre-merge commit, and release/public evidence promotion intentionally leaves reviewed files modified before its PR is merged.

REV31 makes local checkout state an explicit part of the first-real-run provenance chain. Three controller-only stages are inserted immediately after the three evidence merge transitions:

- `qualification-evidence-checkout-reconciled`
- `release-evidence-checkout-reconciled`
- `public-evidence-checkout-reconciled`

`scripts/reconcile_first_real_run_checkout.py` refuses to move the checkout unless all of the following are true:

1. the local branch is the sealed default branch;
2. `origin` identifies the sealed `OWNER/REPO`;
3. GitHub repository ID/default branch/live HEAD match the operational ledger;
4. local HEAD is either the recorded pre-merge source or the exact merge commit;
5. the fetched `origin/<default-branch>` is exactly the ledger merge commit;
6. there are no staged/index changes;
7. every dirty source path is one of the reviewed PR changed paths;
8. every dirty reviewed file that exists locally is byte-identical to the reviewed merge commit blob.

Only after those checks may the tool run `git reset --hard <exact-merge-sha>`. It never runs `git clean`. Operational untracked material under `release/`, `.mte-production-bootstrap.json`, and `first-real-run-ledger.json` is preserved. After the reset, any remaining non-operational dirty path is a failure and Source Integrity must pass.

The reconciliation snapshot is stored in the external first-real-run ledger and includes the previous/local target commits, reviewed changed paths, preserved operational untracked paths, and SHA-256 of the post-reconciliation `SOURCE_SHA256SUMS.txt`. The handoff validator checks this snapshot against the immediately preceding reviewed merge record.

This is operational provenance only. It does not create or satisfy qualification, smoke, signing, Store, or release evidence.
