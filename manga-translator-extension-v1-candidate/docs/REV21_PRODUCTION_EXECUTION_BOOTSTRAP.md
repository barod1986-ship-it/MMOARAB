# REV21 — Production Execution Bootstrap and Ephemeral Signing Provisioning

## Why this revision exists

REV20 closed the final release capsule, but a real execution audit found that infrastructure assumptions were still distributed across workflows. Four protected self-hosted runner roles, qualification/model paths, translation credentials, and public signing credentials had no single contract. More importantly, the public macOS/Windows signing jobs ran on ephemeral GitHub-hosted machines while assuming project-specific local signing state already existed.

REV21 closes those infrastructure/source defects without fabricating any release evidence.

## Production execution contract

`release-control/production-execution-contract.json` is the source-of-truth inventory for:

- the production qualification Linux x86_64 runner labels and `production-qualification` environment;
- Linux/macOS/Windows exact-artifact smoke runner labels/environments;
- required non-secret path variables and secret names;
- canonical Node/npm/Python/uv pins;
- protected release environments;
- public macOS signing/notarization credential names;
- public Windows Artifact Signing OIDC/account/profile settings;
- the manual Chrome 148 + audited-Stable station requirement.

`scripts/probe_production_execution_environment.py` has two modes. Static mode checks the contract against toolchain/workflow source. Live role mode also checks OS/architecture, exact tool versions, secret presence without printing values, and required directory variables. The real qualification and three Engine-smoke jobs call the live probe themselves.

`production-execution-readiness.yml` provides a single operator preflight for the static contract plus the four protected self-hosted runner roles. A missing matching self-hosted runner still remains a GitHub scheduling/administration condition; the workflow cannot manufacture runner capacity.

## macOS public signing fix

The prior job supplied a `MTE_NOTARY_PROFILE` name to a fresh `macos-15` runner but never created that keychain profile and never imported Developer ID private keys. REV21 now:

1. takes Developer ID Application and Installer PKCS#12 material only from protected environment secrets;
2. decodes it into `$RUNNER_TEMP`;
3. creates/unlocks a temporary keychain and imports the identities;
4. materializes a team App Store Connect API private key into `$RUNNER_TEMP`;
5. calls `notarytool` with direct `--key`, `--key-id`, and `--issuer` authentication;
6. removes the keychain and temporary key files at step exit.

`sign-notarize.sh` still supports a pre-existing `MTE_NOTARY_PROFILE` for controlled local operation, but CI does not depend on one.

## Windows public signing fix

The prior job expected `MTE_SIGNTOOL`, dlib, and metadata file paths to exist on `windows-latest`; those are not stable repository assets on an ephemeral hosted image. REV21 replaces that assumption with the official Microsoft Artifact Signing GitHub action, pinned to the audited v2.0.0 commit, and OIDC login pinned to Azure Login v3.0.0.

The protected `release-windows` environment supplies Azure identity secrets plus non-secret Artifact Signing endpoint/account/profile variables. After the service signs all `.exe/.dll/.pyd` files, `verify-package-signed.ps1` requires Windows Authenticode status `Valid` for every PE before creating the final ZIP.

## Required external setup before the first real run

The repository cannot create external credentials or self-hosted machines. The operator must configure:

- runner `mte-production-qualification` on Linux x86_64;
- runner labels `mte-release-linux-x86_64`, `mte-release-macos-arm64`, `mte-release-windows-x86_64`;
- the environment path variables enumerated by the contract;
- `MTE_OPENAI_API_KEY` in each protected smoke environment;
- Developer ID certificates/private keys and team App Store Connect API key in `release-macos`;
- Azure federated identity with Artifact Signing Certificate Profile Signer access plus account/profile settings in `release-windows`;
- protected-environment review policy appropriate to the repository plan;
- real sealed qualification inputs and qualified model bytes on the protected hosts.

No value for any secret is committed, mirrored into readiness JSON, or printed by the probe.

## Non-claims

REV21 does not create dependency locks, production model/corpus bytes, a production freeze, native/browser smoke, Store evidence, signing certificates, Azure resources, Apple credentials, or a final release capsule. Those remain real external execution evidence.
