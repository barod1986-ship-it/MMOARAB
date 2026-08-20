# REV27 — Production Run Authorization and Commit-Transition Provenance

REV27 closes two execution-boundary gaps found after REV26.

First, environment branch protection alone did not prove that the person dispatching a production workflow was an approved release operator. The sealed onboarding configuration now resolves approved GitHub logins to stable numeric actor IDs and provisions `MTE_PRODUCTION_OPERATOR_ID_ALLOWLIST_JSON` as a repository variable. Every production job independently requires `workflow_dispatch`, the repository default branch and membership of `github.actor_id` in that allowlist. Candidate-producing workflows that previously had no protected environment now cross `production-qualification` or `release-candidate` before running.

Second, the first-real-run ledger previously treated an evidence-promotion workflow as if the source tree had already advanced. In reality that workflow opens a PR. REV27 separates **PR created** from **PR merged**, verifies the merge commit's parent and path allowlist, and advances `currentSourceHeadSha` only after the merge is proven. All later workflow runs must use that new commit. Release-smoke promotion follows the same rule, and public V1 has an additional Store/post-Store source transition before finalization.

The ledger is operational state only. It cannot create a lockfile, qualification freeze, smoke result, signature or release-ready artifact, and therefore closes no evidence blocker by itself.
