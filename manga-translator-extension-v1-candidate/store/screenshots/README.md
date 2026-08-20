# Store screenshot capture contract

Do not submit mockups, generated UI, stale screenshots, or copyrighted manga/manhwa pages without permission. Store screenshots must be captured from the exact tested Store candidate in a real supported Chrome build using project-owned or otherwise authorized fixture artwork.

Required capture size for this release contract: **1280×800**, full bleed, square corners, matching the current Store listing documentation. Keep at most five screenshots per locale.

Capture set V1:

1. `01-first-run-privacy.png` — Side Panel first-run disclosure before page access, with no detected image data visible yet.
2. `02-detected-page.png` — Side Panel after activation showing detected visible/near comic images and the Translate Page action.
3. `03-translated-result.png` — Authorized fixture with Arabic dialogue result and clearly preserved SFX; show the extension-owned toggle/restore control.
4. `04-local-engine-setup.png` — Options Local Engine setup showing loopback permission/pairing/profile state without exposing a real pairing token or provider secret.
5. `05-cache-diagnostics.png` — Local cache/diagnostics controls demonstrating user control and no external telemetry claim beyond what the build actually implements.

Localized screenshots may be provided for `en`, `ar`, `ja`, `ko`, `zh_CN`, and `zh_TW`. Screenshot text must match the locale and feature set of the submitted build.

Before upload, run `node scripts/verify-store-assets.mjs store/publication-state.json`; the release-ready gate fails until actual assets are recorded and dimensions/hashes are verified.
