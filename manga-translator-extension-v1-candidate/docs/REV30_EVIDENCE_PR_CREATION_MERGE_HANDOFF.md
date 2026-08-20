# REV30 — Evidence PR Creation and Merge Handoff

REV29 sealed the human review boundaries, but two source-transition boundaries were still asymmetric:

1. local release/public evidence promotion could be recorded before a PR existed, leaving the operational ledger in a dead-end state;
2. merged-PR verification validated an allowlist but did not require the merge to be the exact PR number/head SHA recorded before human review.

REV30 closes both gaps without automating the human merge decision.

## Controller behavior

For `release-evidence-local-promotion` and `public-evidence-local-promotion`, `first_real_run_controller.py advance` now:

1. verifies the local checkout is the ledger default branch at the exact current source commit;
2. verifies Source Integrity and the stage-specific source-transition allowlist;
3. seals `pendingEvidencePr` before any remote mutation, including exact changed paths and SHA-256/size for every promoted file;
4. uses the separate local `MTE_PRODUCTION_EVIDENCE_PR_TOKEN` to create Git blobs/tree/one-parent commit/ref through the Git Database API;
5. creates or recovers one deterministic evidence PR;
6. re-downloads every changed PR file and compares its bytes to the sealed local hashes;
7. records the local-promotion stage and the explicit `*-pr-created` stage atomically, including PR number, branch, head SHA and changed-file hashes.

The tool never performs a general `git push`, never uploads a file outside the stage allowlist, and never stores either local token in the repository or ledger.

## Idempotent recovery

If the controller stops after a branch or PR is created but before the ledger is updated, the sealed `pendingEvidencePr` remains. The next `advance/resume` derives the same deterministic branch, finds the existing PR, revalidates the exact head and remote bytes, and completes the ledger transition without creating a second PR.

## Human merge boundary

At `qualification-evidence-pr-merged`, `release-evidence-pr-merged`, and `public-evidence-pr-merged`, `advance` now uses the previously recorded PR identity. If it is still open, the controller returns a blocked status containing that exact PR. It does not merge it.

After a human merges the PR, the controller requires:

- the same recorded PR number;
- the same recorded head branch and head SHA;
- a merge commit whose first parent is the ledger source cursor;
- only the sealed allowlisted files;
- the live default-branch HEAD to equal that merge commit exactly.

If another commit lands first, the transition is rejected rather than silently skipping over unrelated source changes.

## Qualification evidence PR

`promote-production-qualification.yml` already creates its own reviewed PR. REV30 now binds its branch to both the qualification execute run ID and the controller `run_intent_nonce`. After the workflow succeeds, the controller discovers that exact PR, verifies its one-parent head commit and allowlist, and records its PR number/head SHA before the human merge boundary.

## Token separation

`MTE_PRODUCTION_CONTROLLER_TOKEN` remains local-only and is used for normal orchestration. Required repository permissions:

- Actions: write
- Contents: read
- Pull requests: read

`MTE_PRODUCTION_EVIDENCE_PR_TOKEN` is also local-only and is used only at evidence-PR creation boundaries. Required repository permissions:

- Contents: write
- Pull requests: write

Neither token is an environment/repository secret and neither belongs in onboarding/bootstrap JSON.
