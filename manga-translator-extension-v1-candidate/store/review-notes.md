# Reviewer notes — first public submission

## What the extension does

Manga Translator translates comic image text into Arabic on a page the user explicitly activates. It does not auto-run on every website. The toolbar action opens the Side Panel. On first use, the extension does not inject into or read the current page until the reviewer accepts the in-product privacy disclosure.

## Required companion

Translation processing is performed by the separately installed Local Engine on the same computer. The reviewer build must use the exact signed/attested companion artifact recorded for the Store release. Do not provide an unpublished developer build to reviewers.

Public reviewer instructions are not complete until `store/publication-state.json.publicUrls.engineDownload` points to the tested companion artifact and `reviewerFixture` points to an authorized test page.

## Test path

1. Install the Store candidate ZIP/build in Chrome 148 or newer.
2. Open the authorized reviewer fixture URL supplied in the Dashboard Test instructions.
3. Click the Manga Translator toolbar action.
4. On first run, observe that no page session/images are detected before consent. Read the disclosure and choose **I agree — activate on this page**.
5. Open Settings → Local Engine, grant loopback access from the user gesture, probe the companion, and pair using the companion's locally displayed token.
6. Confirm the release profile reports `ready` and that its privacy descriptor matches the Store disclosure. If that descriptor says any data leaves the device, return to the Side Panel and verify that a **separate remote-transfer disclosure** names the provider and requires an additional affirmative consent before translation can start.
7. Return to the fixture page and translate the page or a visible image.
8. Confirm dialogue/narration is rendered in Arabic and the annotated sound effects remain unchanged.
9. Use **Originals** / the compact page control to restore/toggle without reprocessing.
10. Clear the result cache in Settings and confirm the cache counters return to the expected empty state.

## Network expectations

- Chrome extension ↔ native companion: authenticated loopback only.
- Image CDN access: only an exact optional HTTPS origin after user approval if the normal image path fails.
- No remote executable extension code.
- No external analytics/advertising telemetry in the public V1 configuration.
- Any approved translation-provider traffic must match the profile disclosure and public privacy policy.

## Reviewer credentials

There are no developer-owned website credentials or hidden review accounts. Pairing uses a one-time/local token displayed by the companion. If the final translation provider requires a reviewer API credential, it must be supplied in the Dashboard Test instructions and must not be committed to this repository.
