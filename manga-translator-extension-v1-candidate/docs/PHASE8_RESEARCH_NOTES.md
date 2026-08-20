# Phase 8 research notes — 2026-08-19

## Chrome Web Store privacy baseline

Chrome's July 1, 2026 policy update states that extension user-data collection must be strictly necessary to the disclosed single purpose and that all data collection must be prominently disclosed; enforcement began August 1, 2026.

The User Data FAQ explicitly treats website screenshots/content, requested/interacted domains/URLs, and local-only processing/storage as user-data handling. It also says the prominent disclosure and affirmative consent must occur in the product UI before handling begins; a Store description or privacy policy alone is insufficient for that prominent-disclosure requirement.

This is why Phase 8 changes toolbar activation: first use opens the Side Panel but does not inject/read page data until the disclosure is accepted.

## Minimum permissions

Chrome's User Data FAQ applies the minimum-permission requirement to both required and optional permissions. Phase 8 therefore preserves the existing narrow required permissions and keeps CDN/loopback host access optional and user-triggered.

## Listing and assets

Chrome's current listing documentation requires a 128×128 Store icon, at least one 1280×800 screenshot (up to five), a YouTube promotional-video link, and a 440×280 small promotional tile; the 1400×560 marquee tile is the exception and is optional. Store screenshots/video must reflect the actual extension experience. Phase 8 deliberately does not generate Store evidence because mock or generated UI would not prove the shipped experience.

## Publisher and publication

A Chrome Web Store developer account must be registered and the one-time fee paid. 2-Step Verification is required before publishing/updating. First upload is performed through the Developer Dashboard; after upload, the Store Listing, Privacy, Distribution, and Test instructions tabs become part of the submission workflow.

Phase 8 keeps first submission manual. Automation may be considered only after the item exists and should use the current API rather than building a new dependency on deprecated publication paths.

## WXT browser i18n

WXT 0.21.4 documents that manifest `__MSG_*` localization relies on `public/_locales/<locale>/messages.json`. Phase 8 verifies those catalogs directly. The original Phase 7 artifact already had them; a temporary Phase 8 regression that reduced the catalogs was caught by the inherited checks and restored before release.
