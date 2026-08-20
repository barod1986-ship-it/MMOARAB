# Phase 5B Research Notes — verified 2026-08-19

These notes record why the production benchmark gate compares the current candidates instead of blindly pinning the newest runtime/model. Vendor metrics are **candidate evidence only**; release selection comes from the project's legal manga/manhwa corpus.

## PaddleOCR / PaddlePaddle

- Official PaddleOCR 3.7.0 documentation lists `PP-OCRv6_medium_det` and `PP-OCRv6_small_det`. The documented generic detection Hmean values are 86.2* and 84.1*, with model sizes 59.4 MB and 9.6 MB respectively. Those numbers are not manga-specific.
- Official PP-OCRv6 recognition documentation lists `PP-OCRv6_medium_rec` and `PP-OCRv6_small_rec`; the unified recognizer supports 50 languages for medium/small. The generic recognition averages shown are 83.2* and 81.3*, with model sizes 73.3 MB and 20.4 MB.
- Official PaddleOCR pipeline documentation lists `korean_PP-OCRv5_mobile_rec` as a Korean/English/numeric recognizer, with vendor-reported 88.0 average recognition accuracy and 14 MB model size.
- The official Paddle repository release page currently exposes v3.3.0 as its latest tagged release, while this project separately pins the Python runtime package used by the candidate environment. Runtime version and hardware class are therefore frozen as benchmark inputs; a newer package or tag is never an automatic model winner.

Primary evidence:

- https://paddlepaddle.github.io/PaddleOCR/v3.7.0/en/version3.x/module_usage/text_detection.html
- https://paddlepaddle.github.io/PaddleOCR/v3.7.0/en/version3.x/module_usage/text_recognition.html
- https://paddlepaddle.github.io/PaddleOCR/main/en/version3.x/algorithm/PP-OCRv6/PP-OCRv6.html
- https://github.com/PaddlePaddle/Paddle/releases
- https://github.com/PaddlePaddle/Paddle/issues/77340

## Japanese manga OCR

`kha-white/manga-ocr` explicitly targets Japanese manga and documents vertical/horizontal text, furigana, text over images, varied fonts/styles, low-quality images, and multi-line bubble recognition. This strongly justifies keeping it as a Japanese V1 benchmark candidate, but it does **not** justify preselecting it as the winner. Active v3 compares it with PP-OCRv6 under the same measured CER/latency policy on the project corpus.

Primary evidence:

- https://github.com/kha-white/manga-ocr
- https://huggingface.co/kha-white/manga-ocr-base

## Comic-specialized detector provenance

`dmMaze/comic-text-detector` is a useful specialized challenger, but its repository states that its training mix used Manga109-s, DCM and synthetic data, and explicitly says the authors do not have the right to share the training sets or fonts publicly. The code repository is GPL-3.0, but that alone does not establish redistribution rights for every pretrained weight/data artifact. Phase 5B therefore keeps the weight's artifact-license/provisioning status blocked/pending until independently reviewed.

Primary evidence:

- https://github.com/dmMaze/comic-text-detector

## Inpainting

LaMa and AOT remain separate benchmark candidates. Their repositories publish code and link pretrained checkpoints separately; the exact checkpoint bytes are therefore audited and SHA-pinned independently from the repository code license. Both candidates run on the **same project masks** for a fair comparison.

Primary evidence:

- https://github.com/advimman/lama
- https://github.com/researchmm/AOT-GAN-for-Inpainting

## Arabic font

Noto Sans Arabic is tracked as a separate artifact. Google Fonts ships its OFL 1.1 license and Noto documentation states that Noto fonts can be bundled/redistributed subject to the OFL terms. The exact font bytes still require a SHA-256 pin because a family/repository name is not a stable raster-semantic identity.

Primary evidence:

- https://github.com/google/fonts/blob/main/ofl/notosansarabic/OFL.txt
- https://notofonts.github.io/noto-docs/website/use/

## Release rule

No vendor score in this file can make `default-v1` ready. A production freeze requires:

1. reviewed benchmark-use rights for the external corpus;
2. approved benchmark use for **every artifact actually benchmarked**, including losing candidates;
3. exact local artifact SHA-256 verification;
4. the complete comparison matrix in `benchmark-thresholds-v3`;
5. project quality/human/performance thresholds;
6. exact-zero independent ground-truth SFX destructive-edit metrics;
7. deterministic winner reproduction and a tamper-evident freeze.


## V1 detector candidate revision

The original `benchmark-thresholds-v1.json`/`candidate-plan-v1.json` planned a comic-specialized detector comparison. REV10 preflight found that this candidate lacks a release-qualified pretrained-artifact provenance decision and a production runtime adapter in this repository. Rather than fabricate those prerequisites or let an unresolved research candidate block V1, the active immutable pair is now `benchmark-thresholds-v3.json` + `candidate-plan-v3.json`, comparing the official PP-OCRv6 small and medium detector artifacts on the same project corpus. The old v1 files are retained unchanged as historical evidence. A later v3 policy/plan also supersedes v2 for active V1 use because Japanese OCR must be selected by the same measured CER/latency rule as every other language, not by a hard-coded primary role. Vendor metrics do not choose the V1 winner.
