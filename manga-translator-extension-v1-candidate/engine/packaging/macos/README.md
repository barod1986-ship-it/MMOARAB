# macOS packaging gate

Build natively on the target macOS architecture. Public distribution is blocked until nested Mach-O payloads are Developer ID Application signed with hardened runtime, the installer package is Developer ID Installer signed, Apple notarization succeeds, stapling validates, and a clean-machine smoke test passes.

REV21 explicitly provisions an **ephemeral keychain** on the GitHub-hosted macOS runner. The `release-macos` environment supplies base64-encoded Developer ID Application/Installer PKCS#12 material and passwords; the workflow imports them only into the temporary runner keychain and removes the keychain/files at the end of the signing step. Notarization uses a team App Store Connect API key materialized in `$RUNNER_TEMP` and passed directly to `notarytool` (`--key`, `--key-id`, `--issuer`). `sign-notarize.sh` still supports a local `MTE_NOTARY_PROFILE` for operator use, but CI never assumes that profile already exists.

Required protected inputs are enumerated in `release-control/production-execution-contract.json`; no `.p12`, `.p8`, certificate private key, or notary credential is committed to source.
