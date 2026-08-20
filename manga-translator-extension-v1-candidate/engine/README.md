# Manga Translator Local Engine — Phase 5B Benchmark/Freeze Gate

The Phase 5 staged Engine is retained. Phase 5B adds an auditable release gate before production model revisions are accepted. No model weights are downloaded by the runtime and no production corpus is bundled.

Key developer paths:

- `mte_engine/benchmark/` — corpus, metrics, deterministic selection, gate and freeze logic.
- `benchmark/policies/benchmark-thresholds-v3.json` — active versioned product release policy; v1/v2 remain historical and v3 removes predetermined Japanese OCR preference.
- `model-catalog/model-candidates-v1.json` — model/checkpoint provenance and hash catalog.
- `scripts/*benchmark*`, `validate_corpus.py`, `hash_model_artifact.py` — explicit developer/release tooling.

A production freeze is a necessary gate, not a shortcut: `default-v1` still refuses to become ready until pinned production adapters/provider wiring exists.

---

## Phase 5 staged Engine retained

The loopback-only Engine now contains explicit staged-processing contracts while preserving the Phase 4 durable protocol/security boundary.

## Runtime profiles

- `default-v1`: production profile slot. It stays non-ready until detector/OCR/inpaint benchmark winners, trusted translation configuration, model artifact hashes/licenses, and Arabic font profile are pinned.
- `fixture-v1`: development-only deterministic safety fixture. Hidden unless `MTE_ENABLE_FIXTURE_PROFILE=1`.

For development renderer tests:

```bash
export MTE_ARABIC_FONT_PATH=/absolute/path/to/approved-arabic-font.ttf
export MTE_ENABLE_FIXTURE_PROFILE=1
```

Then run:

```bash
python engine/scripts/run_tests.py
```

The staged pipeline lives under `mte_engine/pipeline/`. Jobs still accept **bytes only**, never image URLs or filesystem paths from the extension/site. Result raster and manifest remain bound to the durable Engine ticket and profile fingerprint.

## SFX invariant

`dialogue|narration` may enter translation/erase/inpaint/render. `sfx|other|uncertain` may not. The Engine dilates a protected mask, rejects destructive/render overlap, recomposites source pixels in protected areas, exact-lossless encodes, decodes the final artifact, then compares protected pixels again.

The test suite includes an independent ground-truth SFX mask so a classifier miss cannot make the preservation metric disappear.


## Phase 7 packaging

The Engine now owns the only non-provider model-download path. It reads a bundled, reviewed distribution catalog; page/job input cannot supply download URLs. Packaging uses a native PyInstaller onedir candidate plus OS-specific release gates. Public Windows/macOS support remains blocked until signed/notarized artifacts and fresh-machine smoke tests pass.
