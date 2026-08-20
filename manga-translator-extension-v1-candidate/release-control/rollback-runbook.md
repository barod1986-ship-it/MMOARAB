# Phase 9 rollback runbook

## Principle

Rollback is an operational recovery action, not a place to add features. Freeze feature work until the incident is closed and the release artifact set is understood.

## Extension rollback

For a public Chrome Web Store release, use the Store rollback function only after confirming that the previous published version is still compatible with the Engine artifacts and model catalog users can obtain. Chrome Web Store rollback restores the previously published version under a new version number; after the rollback, any later fix must again use a newer manifest version.

Before rollback:

1. Freeze rollout percentage increases.
2. Archive the currently deployed Store version, its SHA-256, release manifest and incident notes.
3. Confirm the previous Store artifact hash and its compatible Engine protocol major.
4. Confirm privacy/permission behavior of the previous version is still acceptable.
5. Trigger Store rollback from the dashboard/API as appropriate.
6. Smoke the Store-installed rollback version after Chrome receives it.
7. Publish a support notice if users were affected.

Do not repeatedly alternate rollbacks as a substitute for a fixed release; Chrome rollbacks move to the immediately previous published version, so consecutive rollbacks can cycle between two versions.

## Engine rollback

Engine artifacts are immutable and hash-addressed. Never replace bytes at an existing production URL. To roll back:

1. Stop promoting the affected Engine/model URL.
2. Restore the previously archived compatible artifact URL/catalog entry.
3. Verify URL bytes, size and SHA-256 with `scripts/verify_release_downloads.py`.
4. Re-run clean-machine Engine smoke.
5. Confirm `protocolMajor` remains compatible with the installed extension.

## Data safety

A rollback must not silently resume stale DOM jobs from an earlier browser session. Existing Phase 2–4 stale-target, durable-job and reconciliation rules remain authoritative.
