# Chrome Web Store data inventory — Phase 8

Revision: 2026-08-19.v1

The extension handles user data only for the disclosed manga/manhwa/manhua translation purpose. **Local-only processing** still counts as data handling and is disclosed in-product before the first page activation.

| Data | Why it is handled | Where | Retention / deletion | External sharing |
|---|---|---|---|---|
| Current-page origin | Bind activation, permissions, session freshness, safe diagnostics | Chrome extension trusted storage/session | Session-scoped; safe diagnostics use reduced/derived values | Not sent to a translation provider |
| Comic image bytes | OCR, layout analysis, inpainting, Arabic rendering | Chrome IndexedDB and Local Engine on the same computer | Extension cache follows configured TTL/LRU; user can clear cache | No external image transfer is authorized by the Phase 8 local-processing consent |
| Screenshot crop | Fallback acquisition when direct image access fails | Same as image bytes | Same as image bytes | Same as image bytes |
| OCR text | Translation input | Local Engine | Job lifecycle; terminal Engine spool is cleaned within 24 hours | If the selected qualified profile declares remote OCR-text transfer, a separate versioned in-product disclosure/consent is required and is re-verified by the Local Engine before create/start; public release metadata must match the named provider and frozen profile |
| Translated text | Render translated image and result manifest | Local Engine / local cache | Job/cache lifecycle | Only the selected approved translation profile may return it |
| Generated translated raster | Display result and avoid duplicate processing | Local IndexedDB | Default cache policy is 30 days with LRU/size pressure; user can clear cache | Not shared for advertising/analytics |
| Provider credential | Authenticate a provider if a later approved profile needs one | Local Engine credential storage, not extension storage | Until user removes/reconfigures it | Sent only to its intended provider as required for authentication |
| Pairing token | Authenticate extension ↔ Local Engine | Trusted extension storage and Local Engine config | Until disconnect/re-pair | Never sent to websites or translation providers |
| Local diagnostics | Reliability and troubleshooting | Extension UI/session | Ephemeral unless user explicitly copies them | No external telemetry enabled by default |

## Dashboard classification guidance

Conservatively disclose **Website content** because the extension processes images/text from the activated page. Also disclose the current-page origin under the dashboard category corresponding to **Web history / browsing activity** if that category covers domains or URLs the browser interacts with in the current dashboard wording. Do not claim that the extension collects a browsing-history list: it does not.

No data is sold, used for personalized advertising, credit decisions, or unrelated profiling.
