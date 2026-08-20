# REV26 — Production Workflow Trust Boundary

REV26 closes the GitHub ref/environment trust gap that remained after repository identity binding in REV25.

## Problem closed

The production workflows use `workflow_dispatch`. Repository/source binding proved the intended default-branch commit at onboarding time, but protected environments did not yet require an exact default-branch deployment policy. In addition, `MTE_INFRA_AUDIT_TOKEN` was consumed by a hosted readiness job without an environment boundary.

That combination was unnecessarily permissive: a production workflow could be dispatched for a non-default ref, and the GitHub-side audit credential was not protected by an environment deployment policy.

## New trust boundary

All environments listed in `release-control/production-execution-contract.json` now require `default-branch-only` deployment policy semantics.

The live GitHub audit now records:

- immutable repository ID;
- live default branch;
- environment deployment-branch mode;
- the custom deployment branch policies for each production environment;
- runner state/labels;
- variable names;
- secret names only, never secret values.

A production environment passes only when it uses custom deployment branch policies and contains exactly one branch policy matching the live repository default branch.

`MTE_INFRA_AUDIT_TOKEN` is now an environment secret in `production-infrastructure-audit`. The `github-infrastructure` readiness job references that environment before the token can be consumed.

## Provisioning behavior

New production environments are created with custom branch policies enabled and the live default branch as the sole deployment branch.

Existing environments are intentionally non-destructive:

- already exact-default-branch-only → preserved;
- custom branch mode with zero branch policies → the default branch policy may be added safely;
- protected-branches mode, allow-all mode, or custom policies containing another branch/tag → `apply` fails closed and requires the operator to correct the environment deliberately.

REV26 does not silently delete or rewrite an existing branch policy.

## Token contract correction

`MTE_INFRA_PROVISION_TOKEN` now declares every permission actually used by live provisioning/onboarding:

- `Administration:write`
- `Environments:write`
- `Actions:read`
- `Contents:read`

The last two are necessary for environment discovery and default-branch commit binding respectively.

## Operator flow

The sequence remains:

`template → set-runner ×4 → bind → runner-command → plan --live → apply → verify → production-execution-readiness`

Do not edit the sealed bootstrap JSON manually. Use `set-runner` to change runner mappings.

`verify` is now blocking on default-branch-only environment deployment policies in addition to runner presence, environment names, variables, and secret names.

## Evidence boundary

This revision changes repository/release infrastructure tooling only. It creates no qualification lock, production freeze, smoke observation, orchestration checkpoint, Store evidence, or `release-ready.json`.
