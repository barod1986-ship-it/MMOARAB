# Phase 7 packaging and release runbook

## Release invariants

1. Do not publish without committed `package-lock.json` for the extension and `engine/uv.lock` for the Engine.
2. Use the exact runtime toolchain in `engine/packaging/runtime-versions.json`.
3. Run all Phase 1–7 contracts and Engine tests before packaging.
4. Build the Engine natively on the target OS/architecture. PyInstaller is not a cross-compiler.
5. Generate SBOM/license metadata from locked dependency state. The uv CycloneDX exporter is treated as preview, so its JSON shape is validated before release.
6. Never place signing certificates, private keys, notary credentials, pairing tokens, API keys, or production model weights in the repository.
7. Generate SHA-256 digests for every published artifact and attach GitHub provenance attestations.
8. A candidate can be uploaded for testing while `publicSupportClaimed=false`; it must not be promoted to a public support claim.

## Production model catalog

`engine/model-catalog/model-distribution-v1.json` is intentionally empty until Gate D is frozen. When Gate D is approved:

- add only exact file artifacts with a fixed HTTPS URL, byte count and `sha256:` pin;
- add only reviewed public DNS hosts to `allowedHosts`;
- record SPDX license identifier and redistribution status;
- copy the reviewed catalog byte-for-byte to `engine/mte_engine/resources/model-distribution-v1.json`;
- run Phase 7 contracts and downloader tests;
- do not use URLs supplied by page content, OCR output, translation providers, or Engine jobs.

The installer resumes through HTTP Range into `.part`, validates exact byte count and SHA-256, then performs an atomic rename. A corrupt final artifact is re-queued rather than trusted because a previous database row said `succeeded`.

## Windows candidate

- Build on native Windows using Python 3.13.15, uv 0.12.5 and the exact lock.
- Run `engine/packaging/windows/build.ps1 -Release`.
- Smoke the packaged executable with `engine/packaging/windows/smoke.ps1`.
- For a public claim, authenticate to Microsoft Artifact Signing with GitHub OIDC on the protected `release-windows` environment, sign `.exe/.dll/.pyd` with the pinned `Azure/artifact-signing-action@v2.0.0` commit, verify every PE with `Get-AuthenticodeSignature`, then produce the signed portable bundle. The hosted runner must not depend on repository-specific SignTool/dlib paths.
- Re-run the smoke test on a fresh supported Windows VM with no Python installation.

## macOS candidate

- Build natively on the target architecture.
- Run `engine/packaging/macos/build.sh --release`.
- For public distribution in CI, materialize Developer ID Application/Installer PKCS#12 credentials into an ephemeral runner keychain and use a team App Store Connect API key directly with `notarytool`; delete all temporary key/keychain files in the signing step. Local operator runs may still use an existing `MTE_NOTARY_PROFILE`.
- Verify codesign, package signature, notarization result, stapling and a clean-machine smoke before changing the support claim.

## Linux developer preview

- Build on the oldest distribution baseline selected by the future compatibility matrix rather than only the newest CI runner.
- Run the clean VM smoke on each distribution/glibc combination before claiming support.

## Release metadata

Engine metadata:

```text
cd engine
uv run python scripts/release_metadata.py
```

Extension metadata is generated from the npm lock and built ZIP by `scripts/release-extension-metadata.mjs`.

Expected release metadata includes CycloneDX SBOM, PEP 751 `pylock.toml` for the Engine, model-license inventory, compatibility metadata and SHA-256 sums.
