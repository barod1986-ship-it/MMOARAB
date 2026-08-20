# Production ML Primary-Source Acquisition

## Status

This stage makes production-artifact acquisition auditable without pretending that acquisition is license approval or benchmark approval. The active source identity registry is `engine/model-catalog/acquisition-source-registry-v3.json`; the active benchmark pair is `benchmark-thresholds-v3.json` + `candidate-plan-v3.json`.

The local development environment used for this revision cannot resolve the external model registries, so no missing production artifact hash has been invented. Network acquisition is performed only by an explicit operator action or the manual `acquire-production-ml-artifact` workflow on a runner with network access.

## Automated primary-source artifacts

The registry permits automated acquisition only for the official Paddle OCR detector/recognizer artifacts and the pinned `kha-white/manga-ocr-base` tree. The downloader:

- accepts credential-free HTTPS only;
- restricts initial and redirect hosts to the registry allowlist;
- rejects DNS results that are not globally routable;
- requests identity encoding and enforces per-file byte ceilings;
- uses a staging directory and atomic promotion;
- computes local SHA-256 while streaming;
- emits a content-addressed `.acquisition.json` record; and
- does not change catalog approval fields.

For manga-ocr the upstream Git revision is pinned in the registry, and the large model weight has an upstream-published SHA-256 pin. The complete directory still receives a local tree digest after all required files are acquired.

## Manual-reviewed artifacts

LaMa and AOT intentionally remain manual-derived because the exact checkpoint rights and the local ONNX derivation must be reviewed and recorded separately. The production Arabic font is now an automated `https-zip-member` acquisition pinned to the reviewed Noto Sans Arabic 2.013 release; acquisition still does not grant benchmark or redistribution approval by itself.

## Required chain before benchmark use

1. Verify source identities offline:

   `python engine/scripts/verify_acquisition_sources.py`

2. Acquire an automated artifact explicitly:

   `python engine/scripts/acquire_official_artifact.py --catalog engine/model-catalog/model-candidates-v1.json --source-registry engine/model-catalog/acquisition-source-registry-v3.json --artifact-id <id> --output-dir <dir> --records-dir <dir> --download`

3. Re-verify the local bytes without network access:

   `python engine/scripts/verify_acquisition_record.py --catalog ... --source-registry ... --artifact-id <id> --artifact <path> --record <record>`

4. Perform the separate human provenance/license/redistribution/benchmark-use review.

5. Intake the exact bytes with `intake_model_artifact.py`, supplying both the source registry and acquisition record for automated entries. The provenance receipt copies and binds the acquisition record.

6. Only reviewed, pinned artifacts may enter `prepare_benchmark_run.py` and the formal benchmark executor.

## Japanese OCR policy correction

`candidate-plan-v2` carried `manga-ocr` as a hard-coded Japanese primary and PP-OCRv6 as fallback, while the general product policy said OCR winners should be selected by measured CER with the documented near-quality latency exception. Those rules conflict. Active v3 removes `policyRole` for Japanese: manga-ocr and PP-OCRv6 now compete under the same deterministic selection rule on the project corpus. Historical v1/v2 files are not rewritten.
