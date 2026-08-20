# Manga Translator Privacy Policy

**Policy revision:** 2026-08-19.v1  
**Effective date:** Must be set to the public release date before publication.  
**Support/privacy contact:** `{{SUPPORT_CONTACT_REQUIRED}}`

## Scope

Manga Translator translates manga, manhwa, and manhua images on pages that the user explicitly activates. The extension uses a Local Engine running on the same computer for image processing. This policy covers the Chrome extension and its Local Engine companion.

## Data handled

When the user activates Manga Translator on a supported page, the product may handle the current-page origin, comic image bytes or a visible screenshot crop, OCR text, translated text, generated translated images, local job metadata, settings, pairing information, provider configuration, and reliability diagnostics.

The extension does not scan browsing history in the background. It handles page data only for the user-facing translation workflow on an explicitly activated page.

## First-run disclosure and consent

Before the extension injects its content script or reads comic images for the first time, the Side Panel displays a prominent disclosure explaining the local data handling and requires an explicit acceptance action. The local-processing consent does not authorize transfer of image or text data to an external translation provider.

When a selected ready profile declares that data leaves the computer, the Side Panel presents a separate versioned remote-transfer disclosure before remote-capable work can start. Acceptance is bound to the exact profile fingerprint, privacy descriptor, named provider list, and disclosure version; the Local Engine independently re-validates that proof on job creation and start/resume. A public build still must not enable such a profile unless its frozen release privacy metadata and Store declarations match this actual behavior.

## Local processing

Image acquisition, OCR staging, result caching, and communication with the Local Engine occur on the user's computer. Communication between the Chrome extension and Local Engine is restricted to loopback (`127.0.0.1`) and authenticated with a pairing token. The companion binds only to the fixed local service endpoint defined by the release.

## Translation providers

The production release may expose only translation profiles that passed the project's release gates. The profile capability descriptor states whether image data, OCR text, or visual context can leave the computer. Provider credentials are managed by the Local Engine, not by page content or the content script.

No remote-image or remote-text profile may be enabled for the public Store release unless its disclosure, consent flow, privacy-policy text, and Store dashboard declarations match the actual behavior.

## Storage and retention

- Extension settings remain in local extension storage until changed, cleared, or the extension is removed.
- Runtime session state is transient.
- Translated raster cache is local. The default policy uses a 30-day TTL with size/LRU garbage collection; users can clear it from Settings.
- Local Engine terminal job source/result files are automatically cleaned after at most 24 hours and may be deleted sooner when the job is explicitly deleted.
- Model artifacts are installed locally and remain until removed by the user or companion maintenance tooling.

## Sharing

Manga Translator does not sell user data. It does not share user data with advertising platforms, data brokers, or unrelated analytics services. External telemetry is disabled by default.

If a user selects a separately approved remote translation profile, only the data declared by that profile may be transferred to the named provider as necessary to perform translation. The public release documentation must name those providers before publication.

## Security

The extension uses minimum required permissions, exact-origin optional CDN grants only after an acquisition failure and user approval, trusted-context storage, strict extension messaging checks, and an authenticated loopback protocol. External provider traffic, when a public profile permits it, must use modern encrypted transport.

## User controls

Users can restore original page images, cancel work, clear the local result cache, disconnect the Local Engine, remove optional site permissions through Chrome, and uninstall the extension/companion. Removing the extension clears extension-managed browser storage according to Chrome behavior; companion files are managed separately on the computer.

## Limited Use

User data is used only to provide, maintain, secure, and troubleshoot the disclosed comic-image translation purpose. It is not used for personalized advertising, unrelated profiling, credit decisions, or resale. Human review of user content is not part of ordinary operation.

## Changes

If a release changes data handling, the developer must update this policy, Store privacy declarations, release notes, and in-product disclosure before the changed practice begins. If the change requires new consent, the previous consent version is invalidated.

## Contact

A real monitored support/privacy contact and public URL must replace the placeholder before any Chrome Web Store submission. Phase 8 release verification rejects the placeholder.
