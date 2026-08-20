# Phase 5 Internet Verification Notes — 2026-08-19

Primary/official sources checked before fixing the Phase 5 contracts:

- PaddleOCR main documentation: PP-OCRv6 uses one recognition model for 50 languages including Chinese, English, Japanese, and 46 Latin-script languages. The current text-recognition module separately documents `korean_PP-OCRv5_mobile_rec` for Korean/English/numeric text. This supports the REV10 English/Chinese PP-OCRv6 benchmark lane while retaining the dedicated Korean PP-OCRv5 route.
  - https://paddlepaddle.github.io/PaddleOCR/main/en/index.html
  - https://paddlepaddle.github.io/PaddleOCR/main/en/version3.x/module_usage/text_recognition.html
  - https://paddlepaddle.github.io/PaddleOCR/main/en/version3.x/pipeline_usage/OCR.html
- `kha-white/manga-ocr` official repository: explicitly targets printed Japanese OCR and supports vertical/horizontal text, furigana, text over images, varied fonts/styles, low-quality images, and multi-line bubble recognition in one pass. This supports keeping it as a strong Japanese OCR benchmark candidate; the active v3 policy does not preselect a Japanese winner and requires the project corpus to decide.
  - https://github.com/kha-white/manga-ocr
- Pillow official ImageDraw/ImageFont documentation: `direction="rtl"`, language tags, and complex text shaping require libraqm. The renderer therefore fails closed without RAQM instead of reversing Arabic strings manually.
  - https://pillow.readthedocs.io/en/stable/reference/ImageDraw.html
  - https://pillow.readthedocs.io/en/stable/reference/ImageFont.html
- libraqm official repository: provides bidi support, shaping through HarfBuzz, and script itemization. This is the reference complex-text-layout dependency for the Arabic renderer.
  - https://github.com/HOST-Oman/libraqm
- LaMa official repository/paper and AOT-GAN official repository/paper were rechecked as the two planned inpainting benchmark families. Neither is silently selected as the production default before the project corpus/hardware/license gate.
  - https://github.com/advimman/lama
  - https://github.com/researchmm/AOT-GAN-for-Inpainting

Decision retained: **do not pin a production OCR/detector/inpainting winner from vendor/general benchmarks alone**. The profile remains non-ready until the legal project corpus and exact model artifact revisions/hashes/licenses can be benchmarked and recorded.
