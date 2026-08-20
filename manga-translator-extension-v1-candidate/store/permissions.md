# Permission justifications

These explanations are written for the Chrome Web Store Privacy tab and reviewers.

| Permission | Why the current release needs it | Scope control |
|---|---|---|
| `activeTab` | Gives temporary access to the comic page only after the user activates Manga Translator. | No persistent all-sites required host permission. |
| `scripting` | Injects the runtime content script into the explicitly activated tab so the extension can discover and replace comic images. | Injection is blocked until the first-run privacy disclosure is accepted. |
| `storage` | Stores settings, trusted runtime/session state, pairing configuration, local cache metadata and translated results. | `storage.local` and `storage.session` are restricted to trusted extension contexts. |
| `sidePanel` | Provides the visible user controls for activation, privacy disclosure, translation progress, errors, restore/cancel, and setup. | The panel is opened from the user's extension action. |
| `alarms` | Wakes the deferred retry scheduler for durable translation work after MV3 service-worker suspension. | Uses a single named queue alarm; no browsing/notification behavior. |
| Optional `https://*/*` | Enables an exact HTTPS image-CDN origin only when direct image acquisition fails and the user explicitly approves that specific origin. | Runtime requests are exact-origin; wildcard grants are not automatically requested. |
| Optional `http://127.0.0.1/*` | Connects to the Local Engine on the same computer after the user grants loopback access and pairs the companion. | Engine itself binds only to `127.0.0.1:17891`, requires pairing/authentication, and rejects non-loopback peers. |

## Permissions deliberately not requested

No `<all_urls>`, `tabs`, `history`, `webRequest`, `cookies`, `downloads`, `notifications`, `clipboardRead`, background geolocation, or general filesystem permissions are requested for V1.
