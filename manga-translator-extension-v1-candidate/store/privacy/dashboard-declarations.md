# Chrome Web Store Privacy-tab declarations

Use this file as the reviewer-facing source of truth when completing the Developer Dashboard.

## Single purpose

Translate manga, manhwa, and manhua images on a page the user explicitly activates, using a local companion engine and an approved translation profile, and display the translated raster in the reading experience while preserving sound effects.

## Permissions

Use the justifications in `store/permissions.md`. Do not say a permission is needed by WXT or by the framework.

## Remote code

**No.** The extension package must not download or execute JavaScript, WebAssembly, or other executable extension code from remote servers. Model files downloaded by the separate native companion are data/model artifacts, not remotely executed extension code; they remain subject to the project's model catalog, SHA-256, license, and release gates.

## User-data declarations

Declare website content because the extension processes images and text from the activated comic page, including local-only processing. Conservatively declare the dashboard category corresponding to current-page browsing activity/origin if the current dashboard wording includes domains/URLs the browser interacts with.

The extension does not collect a general browsing-history list, advertising identifiers, financial/payment data, health data, or personal communications as part of its disclosed purpose.

## Limited Use certification

Certify only if the Store candidate still matches `store/privacy/limited-use.md`, the in-product disclosure, the manifest permissions, and the tested code.

## Privacy policy URL

Do not submit until `store/publication-state.json.publicUrls.privacyPolicy` contains the real HTTPS URL serving the reviewed policy text.
