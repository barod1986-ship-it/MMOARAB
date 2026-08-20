# REV14 — Final V1 source audit

Audit date: 2026-08-19

## Verdict

The V1 source implementation is complete after closing the remote OCR-text transfer consent gap. **V1 release readiness remains blocked** until the real qualification/build/browser/native/public evidence passes the existing fail-closed gates.

## Source blocker closed

Production translation is text-only and may send extracted dialogue/narration OCR text to the frozen external provider. REV14 adds a second consent that is separate from local-processing consent and binds acceptance to:

- disclosure revision `2026-08-19.remote-transfer.v1`;
- current `profileId`;
- current `profileFingerprint`;
- exact `imageLeavesDevice` / `ocrTextLeavesDevice` / `visualContextLeavesDevice` descriptor;
- exact external provider list.

The Extension checks the current Engine profile before job create and before every start/resume. The Engine independently checks the same proof on `/v1/jobs` and `/v1/jobs/{ticket}/start`. Unknown transfer behavior, unnamed providers, stale fingerprints, changed privacy descriptors, changed provider lists, or missing proofs fail closed before remote-capable work starts.

## Release-gate hardening

`scripts/verify_remote_transfer_consent_contract.py` validates twelve executable source boundaries. `scripts/verify_controlled_release_ready.py` dynamically runs that source proof whenever the release state claims remote-transfer consent is ready and for every `private-v1`/`public-v1` evaluation. A future `store/release/profile-privacy.json` value cannot by itself satisfy the gate.

`tests/release-ready-gate-smoke.py` includes a negative regression that removes the Extension enforcement marker while leaving the readiness claim true; the verifier must reject it.

## Closed source flags

- `productionRuntimeAdaptersComplete = true` — detector/OCR/role/translator/inpainting runtime adapters are implemented and fail closed for unsupported/unqualified freeze selections.
- `remoteTextTransferConsentReady = true` — separate versioned consent is implemented and enforced on both Extension and Engine boundaries.

These flags describe source implementation only. They do not assert production qualification.

## Evidence blockers intentionally still open

- genuine registry-generated `package-lock.json` and `engine/uv.lock`;
- authorized production corpus and final reviewed artifact decisions;
- exact seven automated acquisitions and reviewed LaMa/AOT runtime packages;
- passing real benchmark plus lock-bound `production-profile-freeze.json`;
- production role/SFX corpus qualification and selected inpainting winner readiness;
- frozen release profile/privacy/provider metadata matching the runnable profile;
- Windows x86_64, macOS arm64, Linux x86_64 final native artifacts and required signing/notarization;
- final SBOM/pylock/model-license metadata;
- fresh Chrome 148/current-Stable and clean-machine Engine smoke bound to the controlled manifest;
- public-only Store/publisher/public URL/support/download/rollback evidence.

## Required next transition

Run the protected real qualification with the sealed operator bundle. Only a passing benchmark may create `production-profile-freeze.json`. Then generate the genuine locks/final native artifacts and execute the controlled release + browser/Engine smoke gates. V1 is releasable only when `npm run check:controlled-release-ready` passes on those exact immutable bytes.
