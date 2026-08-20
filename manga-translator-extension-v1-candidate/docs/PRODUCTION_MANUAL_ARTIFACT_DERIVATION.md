# Production manual artifact derivation — REV10 V1

This stage covers the two V1 artifacts that **must not** be treated as ordinary downloads: `lama-big` and `aot-gan-places2`. The upstream repositories publish Apache-2.0 code, but the pretrained checkpoint bytes are acquired separately. V1 therefore requires a human checkpoint review before an ONNX derivative can enter the benchmark chain.

## LaMa/AOT chain

1. Acquire the checkpoint from the upstream-linked source outside the repository.
2. Hash the exact checkpoint bytes/tree with `engine/scripts/hash_model_artifact.py` or the common SHA tooling.
3. Complete `engine/model-catalog/source-checkpoint-review.template.json`. `benchmarkUseStatus` and `artifactLicenseStatus` must be `approved`; redistribution must be `approved` or `local-only`.
4. Export the checkpoint to ONNX with an explicitly pinned local converter/exporter source. Complete `engine/model-catalog/converter-review.template.json` for those exact converter bytes, URL and revision; converter use and license status must both be `approved`. The exporter is intentionally **not** bundled or auto-downloaded by MTE because upstream checkpoint formats and old PyTorch environments are source-specific and need review.
5. Run `prepare_inpaint_onnx_artifact.py`. It re-hashes the reviewed checkpoint and converter against both review files, loads the ONNX model with CPU ONNX Runtime, executes two pad-aligned dynamic-shape smoke cases, and produces a ZIP that is deterministic for the exact reviewed inputs (the logical derivation timestamp is the later prerequisite-review timestamp) and contains exactly:
   - `model.onnx`
   - `mte-inpaint-contract.json`
   - `mte-derivation.json`
6. Put the resulting ZIP under the manual-artifacts directory and complete the normal `<artifactId>.review.json` decision. `intake_model_artifact.py` does not trust a caller-supplied derivation block: it re-opens the ZIP and copies the packaged derivation evidence into the receipt.

Example:

```bash
python engine/scripts/prepare_inpaint_onnx_artifact.py \
  --artifact-id lama-big \
  --onnx-model /secure/export/model.onnx \
  --source-checkpoint /secure/checkpoints/big-lama \
  --source-review /secure/reviews/lama-big.source-review.json \
  --converter-source /secure/converters/lama-exporter \
  --converter-review /secure/reviews/lama-big.converter-review.json \
  --converter-source-url https://example.invalid/reviewed-converter-source \
  --converter-revision <exact-revision> \
  --operator <reviewer/operator-id> \
  --output '/secure/manual/mte-lama-big-onnx-v1.zip'
```

The derivation manifest stores the SHA-256 and record ID of both the checkpoint review and converter review, plus the converter source SHA/revision/URL. The command must fail if either review does not match the supplied bytes, if ONNX Runtime cannot load the model, or if either smoke shape fails. There is no `--skip-validation` production flag.

## Arabic font

The active V1 font source is now the official upstream `notofonts/arabic` **NotoSansArabic-v2.013** release. It is handled by the primary-source acquirer using `https-zip-member`: only `NotoSansArabic/full/variable/NotoSansArabic[wdth,wght].ttf` is extracted, and the acquisition record binds both the release ZIP SHA-256 and the extracted TTF SHA-256. License/benchmark review remains separate from acquisition.

## Self-hosted qualification

`.github/workflows/qualify-production-ml-self-hosted.yml` is the protected production path. In `prepare` mode, a hosted network job first generates and validates the real npm/uv locks; the self-hosted runner then restores those exact bytes. The runner must have the label `mte-production-qualification`, and `MTE_QUALIFICATION_INPUT_ROOT` must point at an operator-controlled local directory containing the sealed corpus/reviews/manual artifacts. Workflow inputs are **relative paths only** and are rejected if they escape that root or traverse symlinks.

Before any automated model download, prepare mode validates the corpus, every final artifact review, and both LaMa/AOT derived packages. It then acquires exactly the seven automated V1 artifacts, performs reviewed intake, and seals a stable lock-bound run plan. Benchmark execution is a separate `execute` dispatch that restores the same locks/workspace and requires a sealed review for the exact `runPlanSha256`; it never reacquires or re-intakes artifacts. Only safe run-plan/freeze attestations are uploaded. Model bytes, corpus pages, OCR traces and checkpoints remain local. See `docs/REAL_QUALIFICATION_EXECUTION.md`.
