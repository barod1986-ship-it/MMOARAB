# REV24 — Repository Infrastructure Provisioning

REV24 closes the repository-side provisioning handoff that REV22/REV23 could only audit. It still does **not** create release evidence, model artifacts, lockfiles, benchmark results, browser smoke, or a production freeze.

## Bootstrap contract

`release-control/production-execution-contract.json` remains the source of truth. `scripts/provision_github_production_infrastructure.py` is bound to the exact contract SHA-256 and REV24 originally supported five operations; REV25 adds a mandatory sixth operation, `bind`, before any live mutation:

1. `template` — create a sealed but intentionally unbound external bootstrap configuration.
2. `bind` — bind the configuration to the immutable GitHub repository ID, default branch/head, local origin/HEAD, workflow-set hash and Source Integrity hash.
3. `plan` — show required mutations without exposing any values.
4. `runner-command` — produce an OS-appropriate registration command for one existing runner installation directory. The registration token is requested just-in-time and kept only in memory.
5. `apply` — create missing environments, set environment variables/secrets from local environment variables, and add required custom runner labels.
6. `verify` — run the same GitHub-side audit used by production readiness after provisioning.

The committed `release-control/production-infrastructure-bootstrap.example.json` contains **source environment-variable names only** and placeholder runner names. It is not a credential file.

## Operator flow

Generate a local configuration outside source or at the ignored `.mte-production-bootstrap.json` path:

```bash
python scripts/provision_github_production_infrastructure.py template \
  --repository OWNER/REPO \
  --output .mte-production-bootstrap.json
```

REV25 corrects an operational flaw in the original REV24 instructions: manual edits would invalidate `configSha256`. Configure each runner through `set-runner`, which validates the name and reseals the config:

```bash
python scripts/provision_github_production_infrastructure.py set-runner --config .mte-production-bootstrap.json --role qualification-linux-x86_64 --name mte-qualifier-01
```

Repeat for all four roles. Then, from the synced default branch of the intended repository, bind the config:

```bash
python scripts/provision_github_production_infrastructure.py bind --config .mte-production-bootstrap.json
```

After binding, export each local source variable named by `environmentVariables` and `environmentSecrets`. Secret values must stay in the operator environment/secret manager; do not write them into the bootstrap JSON.

For each runner host, generate the registration command and run it from an unpacked GitHub Actions runner directory:

```bash
python scripts/provision_github_production_infrastructure.py runner-command \
  --config .mte-production-bootstrap.json \
  --role qualification-linux-x86_64
```

The command requests a short-lived repository registration token immediately before `config.sh`/`config.cmd` and does not persist it.

Then provision repository metadata using a **separate write-scoped operator token** in `MTE_INFRA_PROVISION_TOKEN`:

```bash
python scripts/provision_github_production_infrastructure.py plan --config .mte-production-bootstrap.json --live
python scripts/provision_github_production_infrastructure.py apply --config .mte-production-bootstrap.json
python scripts/provision_github_production_infrastructure.py verify --config .mte-production-bootstrap.json
```

`apply` is deliberately non-destructive: existing environments are preserved rather than rewritten, existing protection rules are not replaced, and runner custom labels are added rather than replacing all labels. Environment secrets are passed to `gh secret set` over stdin; their values are not included in the plan/apply report.

After `verify` passes, dispatch `.github/workflows/production-execution-readiness.yml`, then record its run ID in the REV24 first-real-run ledger and proceed in the contract order.

## Token separation

`MTE_INFRA_PROVISION_TOKEN` is an operator/bootstrap credential and is not the same as `MTE_INFRA_AUDIT_TOKEN`. The provisioning token requires repository administration/environment **write** capability for environment creation, runner registration/labels, variables and secrets. The readiness audit token remains read-only and is what the workflow uses after bootstrap.

## Safety properties

- no secret value is stored in the committed example or bootstrap reports;
- configuration is contract-bound and content-addressed;
- tampering with repository/runner mappings invalidates `configSha256`;
- existing environment protection rules are not silently reset;
- runner registration tokens are not written to disk by the generated command;
- provisioning success does not close any V1 release gate by itself.

## Resume launch hints

The REV24 contract also maps every first-real-run stage to its workflow/tool or manual boundary. `first_real_run_handoff.py init`, `record`, and `status` return `nextStageLaunch`, so the operator is not forced to reconstruct which workflow belongs to the next ledger stage. These are launch hints only; successful workflow run IDs still have to be recorded and all release evidence is independently verified by the downstream gates.

## REV25 identity-binding successor

REV24's provisioning primitives remain in use, but live mutation is now preceded by REV25 repository onboarding. A generated config is intentionally **unbound** until `bind` proves the immutable GitHub repository ID, live default branch/head, local origin/HEAD, production workflow-set hash and Source Integrity hash. See `docs/REV25_REPOSITORY_ONBOARDING_IDENTITY_BOUND.md`. Runner registration, live planning, apply and verify reject an unbound config.
