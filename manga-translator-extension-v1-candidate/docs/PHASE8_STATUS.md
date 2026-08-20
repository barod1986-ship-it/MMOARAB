# Phase 8 status — Chrome Web Store readiness

Revision: REV10 / 2026-08-19

## Scope completed

Phase 8 adds the optional public Chrome Web Store release layer without weakening the Phase 5B/7 production gates.

Implemented:

- versioned first-run prominent privacy disclosure and affirmative consent before any page injection/image handling;
- consent invalidation when the disclosure version changes;
- complete `public/_locales` manifest catalogs, including the manifest `__MSG_*` keys;
- Store listing drafts for `en`, `ar`, `ja`, `ko`, `zh_CN`, and `zh_TW`;
- single-purpose declaration and explicit excluded-purpose boundaries;
- user-data inventory, Limited Use statement, dashboard declaration guide, and public privacy-policy draft;
- permission justifications for required and optional permissions;
- reviewer test path and a project-controlled reviewer-fixture specification;
- real-screenshot and Store-asset contracts (no generated/mock product screenshots accepted);
- publisher/2-Step Verification/manual-first-submission checklist;
- machine-readable publication state that defaults to fail-closed/manual blockers;
- exact tested-ZIP → Store-candidate promotion with byte-for-byte copy and SHA-256 verification;
- strict Store-release verifier that also supports a synthetic fully-ready positive test;
- GitHub Actions workflow that can build/test/promote a Store candidate but does not auto-submit the first Store item.

## Browser-i18n regression protection

The original Phase 7 ZIP already contained the required `public/_locales/<locale>/messages.json` catalogs for the manifest `__MSG_*` keys. An intermediate Phase 8 edit temporarily reduced those catalogs; the inherited Phase 6 regression gate caught the loss. The full catalogs were restored from the original Phase 7 artifact, English/Arabic were extended with the new privacy strings, and Phase 8 now verifies the manifest-localization keys so this regression cannot pass silently.

## Privacy gate

The extension no longer creates a page session or injects the content script on first toolbar activation until the user accepts the versioned disclosure in the Side Panel. The disclosure states the current-page/image/OCR/result data involved, its local use, retention controls, and that the local-processing consent does not authorize external-provider transfer.

Consent is product-level. If the user accepts while an unsupported internal Chrome page is active, consent is stored but no page activation occurs; activation is still limited to explicit HTTP(S) tabs.

A future profile that sends image/OCR/visual-context data off-device remains a public-release blocker until its frozen privacy descriptor, named provider(s), and a separate versioned remote-transfer consent path are implemented.

## Verification actually run in this environment

- `npm run check:offline`: passed.
- Phase 1 offline checks: 15/15.
- Phase 2 checks: 5/5.
- Phase 3 checks: 6/6.
- Phase 4 contracts: 42/42.
- Phase 5 contracts: 20/20.
- Phase 5B contracts: 33/33.
- Phase 6 contracts: 30/30.
- Phase 7 contracts: 82/82.
- Phase 8 contracts: 151/151.
- Total inherited/offline/contract checks represented above: 384, plus 2/2 Store tooling smoke checks.
- Python Engine tests: 46/46.
- `tsc -p tsconfig.structural.json --noEmit`: passed.
- Python `compileall`: passed.
- Phase 1 fixture manifest validation: passed.
- All eight GitHub workflow YAML files parse successfully.
- Store tooling smoke: 2/2 (exact-copy promotion + positive fully-ready release gate).
- Negative Store asset gate: correctly blocked with 9 missing-real-asset blockers.
- Negative real Store-release gate: correctly blocked with 25 unresolved manual/production blockers.
- Exact tested-ZIP promotion rejects a deliberately wrong SHA-256.

## Public Store exit gate: NOT passed

This is intentional. Current blockers include:

- public distribution decision not recorded;
- developer account/registration fee/publisher ownership/contact/2-Step Verification not verified;
- public HTTPS privacy/homepage/support/reviewer-fixture/Engine-download URLs not supplied;
- no real 128×128 Store icon, 440×280 promo tile, required real YouTube promo video, or real localized product screenshots recorded;
- Developer Dashboard listing/privacy/distribution/test-instruction/first-manual-submission steps not completed;
- Phase 5B production profile freeze not ready;
- Phase 7 signed native companion support gate not ready;
- Chrome 148 and current-Stable Store-candidate smoke tests not run;
- production profile privacy fingerprint/descriptor not frozen;
- privacy-policy support contact placeholder is intentionally unresolved;
- no real WXT Store candidate exists because npm registry access is unavailable in this environment.

`package-lock.json` is still not fabricated. A final `npm install --package-lock-only` attempt on 2026-08-19 timed out.

## Release invariant

The Store upload must be the same ZIP bytes that passed the release test. `prepare_store_candidate.py` refuses hash drift, validates the built manifest and permission set, and copies the ZIP without re-zipping. `candidate.json` must prove `testedSha256 == sha256`, and the verifier re-hashes the candidate bytes.

## Official sources reviewed

- Chrome Web Store 2026 policy update: https://developer.chrome.com/blog/cws-policy-updates-2026
- User Data FAQ / prominent disclosure: https://developer.chrome.com/docs/webstore/program-policies/user-data-faq
- Program Policies: https://developer.chrome.com/docs/webstore/program-policies/policies
- Listing fields/assets: https://developer.chrome.com/docs/webstore/cws-dashboard-listing
- Image requirements: https://developer.chrome.com/docs/webstore/images
- Publishing flow: https://developer.chrome.com/docs/webstore/publish
- Developer registration: https://developer.chrome.com/docs/webstore/register
- 2-Step Verification: https://developer.chrome.com/docs/webstore/program-policies/two-step-verification
- WXT i18n: https://wxt.dev/guide/essentials/i18n
