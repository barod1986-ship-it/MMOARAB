# REV22 — GitHub infrastructure audit and first-real-run handoff

## Why this revision exists

REV21 can prove that a job which has already landed on a protected self-hosted runner has the correct OS, architecture, toolchain and protected path/secret presence. It could not prove the GitHub-side facts **before** scheduling the expensive production chain: that the required runner labels resolve to online runners, that all protected environments exist, or that required environment variable/secret names are actually configured.

REV22 closes that repository-administration visibility gap without reading or exporting any secret value.

## GitHub-side audit

`scripts/audit_github_production_infrastructure.py` audits the repository metadata required by `release-control/production-execution-contract.json` using the versioned GitHub REST API. It checks:

- every protected environment named by the production contract exists;
- every self-hosted role has at least one **online** repository runner whose labels contain the complete required label set;
- each protected environment contains the required variable names;
- each protected environment contains the required secret names;
- public macOS and Windows signing environment configuration names are present;
- required-reviewer / prevent-self-review recommendations are reported separately as warnings unless the contract explicitly promotes them to blocking policy.

GitHub's secret-listing API returns secret metadata/names, not plaintext secret values. The audit output therefore contains names and runner/environment metadata only. The audit token itself is never emitted.

## Audit token

The single operator bootstrap secret is `MTE_INFRA_AUDIT_TOKEN`. For a repository-scoped fine-grained token, the audit needs repository **Administration: read** to list repository self-hosted runners and **Environments: read** to inspect environment configuration. It does not need write access and does not provision or mutate infrastructure.

The token remains a repository/organization administration bootstrap credential; it is not copied into runtime, qualification inputs, release evidence, or the final release capsule.

## Unified readiness workflow

`.github/workflows/production-execution-readiness.yml` now executes in this order:

1. static source/contract verification;
2. GitHub-side infrastructure audit;
3. live qualification runner probe;
4. live Linux/macOS/Windows smoke-runner probes.

The live runner jobs depend on a successful GitHub-side audit, so an absent environment, missing required configuration name, or offline/mislabelled runner is detected before the production chain begins.

## First-real-run order

The production contract now records the canonical first-run order as machine-readable metadata:

`GitHub infrastructure audit → live runner readiness → qualification prepare → benchmark review → qualification execute → evidence promotion → exact artifact builds → controlled assembly → native smoke → Chrome 148 + audited Stable smoke → evidence promotion → final gate/capsule`.

Manual review boundaries remain explicit. Resume must use the recorded workflow run IDs / content-addressed evidence; no stage may silently rebuild or substitute a prior artifact.

## External facts still required

REV22 does not create runners, environments, secrets, variables, signing accounts, qualification inputs, locks, a production freeze, smoke observations, Store evidence or a final release capsule. Those must be configured or generated in the real production repository. A missing `MTE_INFRA_AUDIT_TOKEN` therefore causes the unified readiness workflow to fail closed rather than treating the GitHub administration layer as implicitly ready.
