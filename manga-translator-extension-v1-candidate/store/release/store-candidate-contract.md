# Store candidate artifact contract

The Chrome Web Store upload ZIP must be byte-for-byte the ZIP that passed the release smoke tests.

Workflow:

1. Build one extension ZIP from committed, locked dependencies.
2. Run all release checks against that ZIP/build.
3. Record SHA-256 as the tested artifact digest.
4. Run `python scripts/prepare_store_candidate.py --zip <zip> --tested-sha256 <digest>`.
5. The script re-hashes the input, inspects the ZIP for forbidden files and manifest scope, then copies **the same bytes** to `release/store/` and writes candidate metadata.
6. Compare the Developer Dashboard upload file digest to `release/store/SHA256SUMS` before upload.
7. Never rebuild or re-zip after the final smoke test. Any rebuild creates a new candidate and requires repeat testing.

First publication remains a manual Dashboard step. CWS API V2 automation is reserved for later updates after the item exists and the release process has been validated.
