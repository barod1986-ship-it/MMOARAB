# Production benchmark corpus

Do **not** commit copyrighted manga/manhwa/webtoon pages to this repository unless redistribution is explicitly authorized.

The release corpus is external and must be described by `corpus-manifest.json`. Every page entry records a SHA-256 for the image and annotation plus a reviewed benchmark-use rights basis/source. The production gate intentionally refuses unreviewed pages.

Initial REV10 target:

- 60–100 English-translated manga/manhwa/webtoon pages (primary path).
- 10–20 Japanese fallback pages.
- 10–20 Korean fallback pages.
- 10–20 Simplified/Traditional Chinese fallback pages.
- Independent ground-truth SFX annotations; at least 10 SFX-bearing pages for the exact-zero release gate.
- At least 5 clean-reference pages for quantitative inpainting checks.

Required visual coverage is enforced by the validator. The repository includes no production corpus images.
