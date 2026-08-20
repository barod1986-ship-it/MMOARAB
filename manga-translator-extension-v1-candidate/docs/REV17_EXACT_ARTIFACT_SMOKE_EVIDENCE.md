# REV17 — Exact artifact smoke evidence pipeline

## Goal

Close the path from one immutable V1 controlled archive to evidence that proves the **same bytes** were exercised on all supported native targets and on Chrome 148/current Stable. This revision defines and verifies the collection path; it does not create a passing observation without a real run.

## 1. Controlled archive identity

`controlled-release.json` schema v2 carries `sourceHeadSha` and exact hashes for the Extension and every Engine artifact. V1 metadata includes the byte-identical `production-profile-freeze.json`. Native/browser observations must carry the SHA-256 of this manifest plus the exact artifact filename/hash they exercised.

## 2. Native exact-artifact smoke

Run `.github/workflows/smoke-controlled-release-engine.yml` against a successful `controlled-release.yml` run from the same commit. Protected runner labels are:

- `mte-release-linux-x86_64` / environment `release-smoke-linux`;
- `mte-release-macos-arm64` / environment `release-smoke-macos`;
- `mte-release-windows-x86_64` / environment `release-smoke-windows`.

Each environment must provide `MTE_QUALIFIED_MODEL_ARTIFACTS_DIR`; the translation smoke also requires the protected `MTE_OPENAI_API_KEY` secret for the currently frozen text-only production translator. The smoke tool re-hashes all selected model/font bytes against the controlled freeze and checks that the freeze source binding matches the exact checkout.

Portable ZIP/TAR Engine artifacts are extracted into a clean temporary directory. A macOS `.pkg` is different: signature, stapling and Gatekeeper checks are run, the exact package is installed with the system installer, smoke runs from `/Applications/Manga Translator Engine/mte-engine`, then the installed tree and package receipt are removed before the observation can be written. The protected macOS runner therefore needs non-interactive sudo for only those installer/cleanup commands and must start without that product installed.

No corpus page, OCR trace, model checkpoint, API key or pairing token is uploaded as evidence. Only observation JSON and a derived profile/privacy candidate are uploaded/attested.

## 3. Per-target profile fingerprint, common privacy

`default-v1` fingerprinting includes packaged runtime/codec identity. Linux, macOS and Windows can therefore produce different fingerprints even when they are the same approved profile in semantic terms. `scripts/materialize_release_profile_privacy.py` requires exactly one observation from each native target and produces schema-v2 `profileFingerprintsByTarget`.

Cross-platform drift is still forbidden for:

- `imageLeavesDevice`;
- `ocrTextLeavesDevice`;
- `visualContextLeavesDevice`;
- exact external provider list.

The descriptor is also bound to the controlled manifest hash and `sourceHeadSha`.

## 4. Real Chrome acceptance

On a clean GUI machine, run the recorder twice, once with a Chrome 148 binary and once with the current Stable binary. Example:

```bash
python scripts/record_exact_browser_smoke.py \
  --controlled-manifest release/controlled/<release-id>/controlled-release.json \
  --orchestration-session <native-smoke-complete.json> \
  --chrome <path-to-real-chrome> \
  --expected-major 148 \
  --engine-target <native-target-on-this-machine> \
  --fixture-url http://127.0.0.1:<port>/<authorized-fixture> \
  --output release-smoke/chrome-148.json
```

Repeat for the audited current Stable major. The recorder verifies the Chrome major, uses a fresh temporary browser profile, re-hashes the exact controlled Extension ZIP and selected Engine archive, and refuses non-interactive execution. The operator must explicitly confirm the four user-visible lifecycle checks while that exact launched process is running.

## 5. Transactional evidence promotion

After the three native and two browser records exist, first advance the REV18 session to `browser-smoke-complete`, then promote:

```bash
python scripts/promote_release_smoke_evidence.py \
  --controlled-manifest release/controlled/<release-id>/controlled-release.json \
  --orchestration-session <browser-smoke-complete.json> \
  --engine-observation <linux.json> \
  --engine-observation <macos.json> \
  --engine-observation <windows.json> \
  --browser-observation <chrome-148.json> \
  --browser-observation <chrome-stable.json>
```

REV18 extends this command: it stages profile/privacy, smoke records, release state, the `evidence-promoted` orchestration checkpoint, and the updated source-integrity manifest. It promotes them only after every target, hash, source identity, browser major, profile fingerprint and privacy/provider contract validates. A failed validation or post-write source-integrity check restores the prior evidence state.

Then run:

```bash
npm run check:controlled-release-ready
```

For a public V1, Store-installed smoke and the remaining publication/support/download/rollback gates are additional requirements.
