# Phase 8 Chrome Web Store readiness runbook

This runbook is fail-closed. Do not mark a field true merely because a document exists; mark it only after the actual Dashboard/account/artifact step has completed.

## 1. Finish production gates first

1. Complete Phase 5B with the real licensed corpus and hashed model artifacts.
2. Freeze `default-v1`, run exact controlled Engine smoke on Linux/macOS/Windows, and derive the approved per-target profile fingerprints plus one common privacy/provider descriptor with `scripts/materialize_release_profile_privacy.py`. Do not copy a single fingerprint by hand.
3. Complete Phase 7 signed/native artifacts and clean-machine smoke tests for every OS you intend to claim publicly.
4. Create real `package-lock.json` and `engine/uv.lock` from successful online resolution; do not hand-write either lock.

## 2. Publisher setup

1. Register the Chrome Web Store developer account and pay the registration fee.
2. Enable and verify 2-Step Verification.
3. Verify publisher/contact information and ownership.
4. Record only completed facts in `store/publication-state.json`.

## 3. Public URLs

Host stable HTTPS pages for:

- privacy policy;
- product/home page;
- support/contact page;
- reviewer fixture;
- Local Engine downloads for only the OS targets whose release gates passed.

Remove `{{SUPPORT_CONTACT_REQUIRED}}` from `store/privacy/privacy-policy.md` only after a real monitored contact is chosen.

## 4. Capture real Store assets

Follow `store/screenshots/README.md` and `store/assets/README.md`.

Required V1 capture set uses the exact Store candidate and an authorized fixture. Record the required real YouTube promotional video as well. Do not use mockups, image-generator UI, or random copyrighted manga pages as evidence of the actual product.

Record paths in `store/publication-state.json`, then run:

```bash
npm run check:store-assets
```

## 5. Build and test the extension candidate

On a connected release environment:

```bash
npm ci
npm run check
npm run check:phase8-contracts
npm run check:store-tools
npm run zip
```

Run Store/reviewer smoke on Chrome 148 and the current Stable channel. Test first-run consent from clean extension storage.

## 6. Promote the exact tested bytes

Compute the tested ZIP digest, then:

```bash
python scripts/prepare_store_candidate.py \
  --zip .output/<tested-extension>.zip \
  --tested-sha256 <sha256>
```

The promotion script does not re-zip. Verify:

```bash
node scripts/verify-store-release-ready.mjs release/store/candidate.json
```

Optional hash fields in `publication-state.json` may mirror the final digest, but the authoritative evidence is the generated `candidate.json` plus a re-hash of the copied bytes.

## 7. First Store submission

The first public Store item is intentionally a manual Dashboard flow:

1. Upload the exact `release/store/*.zip` candidate.
2. Complete Store Listing from `store/listing/*` and real assets.
3. Complete Privacy using `store/privacy/*` and `store/permissions.md`.
4. Complete Distribution deliberately (private/unlisted/public and regions).
5. Copy reviewer instructions from `store/review-notes.md` and the real fixture URL.
6. Re-check all declarations against actual network behavior and permissions.
7. Submit for review; use deferred publishing if release timing needs separation from approval.

Do not add automated Store publication until the item already exists and the publisher workflow is intentionally migrated to the current Chrome Web Store API.

## 8. Evidence to archive

Archive together:

- tested Store ZIP;
- candidate ZIP (same bytes);
- SHA-256 and `candidate.json`;
- extension SBOM/metadata and provenance attestation;
- frozen production profile and model/license evidence;
- signed companion artifacts and hashes;
- Store screenshots/icon/promo hashes;
- clean-machine/Chrome smoke results;
- final listing/privacy/permission/reviewer text submitted to the Dashboard.

## REV19 exact controlled public-V1 handoff

For a real public V1, do not build a fresh Store ZIP from the source checkout. Run `prepare-store-candidate.yml` with the successful public-V1 controlled-release run. The workflow verifies the tracked `evidence-promoted` orchestration checkpoint, runs the pre-Store public gate, seals `release/store/store-submission-handoff.json`, and copies the exact controlled Extension ZIP into `release/store` with schema-v2 `candidate.json` binding.

After manual Store upload/staging, run `scripts/record_store_installed_smoke.py` twice on clean GUI machines: Chrome 148 and the current Stable major recorded by `release-control/release-state.json`. Once all public publisher/support/download/rollback facts are true, promote the two Store observations with `scripts/promote_public_release_evidence.py`. Public finalization is allowed only from `public-evidence-promoted`; see `docs/REV19_PUBLIC_STORE_EVIDENCE_CLOSURE.md`.
