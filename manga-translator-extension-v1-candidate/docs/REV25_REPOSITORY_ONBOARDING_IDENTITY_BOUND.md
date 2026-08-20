# REV25 — Repository Onboarding Identity Binding

REV25 hardens the last operator-controlled boundary before production infrastructure is mutated. REV24 proved that the required environments, variables, secret names and runner labels can be provisioned without storing credential values; REV25 additionally proves that the provisioning configuration belongs to the **intended GitHub repository and exact default-branch source revision**.

This layer remains operational bootstrap state only. It does not create dependency locks, qualification evidence, production freeze, smoke evidence, signatures, Store evidence, orchestration evidence or `release-ready.json`.

## Required flow

Create the external bootstrap config as before:

```bash
python scripts/provision_github_production_infrastructure.py template \
  --repository OWNER/REPO \
  --output .mte-production-bootstrap.json
```

Do not edit the sealed JSON manually. Configure each runner mapping through the resealing CLI command, for example:

```bash
python scripts/provision_github_production_infrastructure.py set-runner \
  --config .mte-production-bootstrap.json \
  --role qualification-linux-x86_64 \
  --name mte-qualifier-01
```

Repeat `set-runner` for the four roles. Runner names use conservative ASCII (`A-Z`, `a-z`, digits, `.`, `_`, `-`). Secret values never belong in this file.

Then, from the checked-out **default branch of the actual project repository**, export `MTE_INFRA_PROVISION_TOKEN` and bind the config:

```bash
python scripts/provision_github_production_infrastructure.py bind \
  --config .mte-production-bootstrap.json
```

`bind` fails unless all of the following are simultaneously true:

- the local `origin` resolves to the same `OWNER/REPO` in the config;
- the local branch is GitHub's live default branch;
- local `HEAD` equals the live GitHub default-branch head;
- GitHub's immutable repository ID and returned `full_name` match the target;
- all 16 production workflows declared by the production contract are present locally;
- the workflow-set SHA-256 and current `SOURCE_SHA256SUMS.txt` SHA-256 can be sealed into the binding.

After binding, all mutation-capable operations require the sealed `repositoryBinding`:

```bash
python scripts/provision_github_production_infrastructure.py runner-command --config .mte-production-bootstrap.json --role qualification-linux-x86_64
python scripts/provision_github_production_infrastructure.py plan --config .mte-production-bootstrap.json --live
python scripts/provision_github_production_infrastructure.py apply --config .mte-production-bootstrap.json
python scripts/provision_github_production_infrastructure.py verify --config .mte-production-bootstrap.json
```

`plan --live`, `apply`, and `verify` re-read the live repository identity and default-branch head and reject drift. Generated Bash/PowerShell runner-registration commands also re-check the repository ID/head before requesting the short-lived registration token.

## Shell-safety closure

REV24 accepted arbitrary runner-name text and interpolated repository/runner values into generated shell commands. REV25 treats that as unsafe input. Repository identifiers now use a conservative `OWNER/REPO` grammar, runner names use a conservative ASCII grammar, Bash values are shell-quoted, and PowerShell values are single-quote escaped. A modified bootstrap config cannot turn a runner name into an operator-shell command.

## First-real-run ledger binding

The first-real-run ledger no longer accepts a manually typed source SHA during initialization. It must inherit repository ID, repository name, default branch, source head, workflow-set hash and bootstrap-config hash from a valid sealed onboarding config:

```bash
python scripts/first_real_run_handoff.py init \
  --output /secure/operator-state/mte-v1-first-run.json \
  --release-id v1.0.0-rc1 \
  --release-class private-v1 \
  --onboarding-config .mte-production-bootstrap.json
```

This prevents the operator ledger from pointing at a different commit than the one whose infrastructure was provisioned.
