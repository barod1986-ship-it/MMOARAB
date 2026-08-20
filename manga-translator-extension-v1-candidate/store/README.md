# Chrome Web Store submission source tree

This directory contains reviewed source material and fail-closed state for an optional public Chrome Web Store release.

- `single-purpose.json` — canonical product purpose and excluded-purpose boundaries.
- `listing/` — locale-specific listing drafts.
- `privacy/` — data inventory, Limited Use statement, dashboard declarations, and privacy-policy draft.
- `permissions.md` — permission-by-permission justification.
- `review-notes.md` and `reviewer/` — reviewer path and fixture contract.
- `screenshots/` and `assets/` — real-product asset requirements; no placeholder graphics are accepted as release evidence.
- `publisher/` — manual publisher/account checklist.
- `release/` — privacy/profile and exact-artifact release contracts.
- `publication-state.json` — fail-closed record of manual/public release facts. `false`/`null` means not verified, not “unknown but assumed OK”.

Run `npm run check:phase8-contracts`, `npm run check:store-tools`, `npm run check:store-assets`, and finally `npm run check:store-release-ready` as appropriate.
