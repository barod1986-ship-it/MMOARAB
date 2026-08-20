# Windows packaging gate

The Phase 7 candidate is an **onedir** companion built on native Windows. A public Windows claim remains blocked until every PE payload is Authenticode-signed and verified, the signed bundle is built from the locked release environment, and a fresh Windows VM smoke test passes.

REV21 removes the former assumption that a GitHub-hosted runner already contains project-specific `SignTool`/dlib/metadata paths. `release-engine-windows.yml` authenticates to Microsoft Artifact Signing with GitHub OIDC (`azure/login`), signs the exact `.exe/.dll/.pyd` payload with the pinned `Azure/artifact-signing-action@v2.0.0` commit, then runs `verify-package-signed.ps1` to require `Get-AuthenticodeSignature` status `Valid` on every PE file before the final ZIP is created.

The `release-windows` environment must provide the Azure identity secrets and Artifact Signing account/profile variables documented in `release-control/production-execution-contract.json`. No signing private key or dlib is stored in the repository.
