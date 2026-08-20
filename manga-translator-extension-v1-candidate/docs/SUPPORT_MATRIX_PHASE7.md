# Phase 7 support matrix

This matrix describes **release candidates**, not public support claims. `engine/packaging/support-claims.json` is the machine-readable authority.

| Target | Phase 7 status | Public support | Required before public claim |
|---|---|---:|---|
| Windows x86_64 | release candidate | No | locked dependencies, Authenticode verification, provenance attestation, clean Windows VM smoke |
| macOS arm64 | release candidate | No | locked dependencies, Developer ID Application/Installer signing, hardened runtime, notarization, stapling, provenance attestation, clean machine smoke |
| Linux x86_64 | developer preview | No | locked dependencies, provenance attestation, measured distro/glibc matrix, clean VM smoke |

The extension and Local Engine are separate artifacts. The extension never downloads or executes a companion binary. Large model files are installed only by the authenticated Local Engine from its reviewed distribution catalog.

## Browser baseline

The extension baseline remains Chrome 148+. A browser artifact must not be described as release-tested until it has passed the Phase 6/7 acceptance flow in a real Chrome 148+ build.
