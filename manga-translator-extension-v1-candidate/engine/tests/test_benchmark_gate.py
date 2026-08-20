from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from mte_engine.benchmark.catalog import CatalogError, load_catalog
from mte_engine.benchmark.common import canonical_json, sha256_bytes, sha256_path
from mte_engine.benchmark.corpus import CorpusError, load_corpus, production_corpus_gate, validate_corpus
from mte_engine.benchmark.corpus_sources import load_source_registry, source_registry_digest
from mte_engine.benchmark.freeze import build_freeze, load_freeze, validate_freeze
from mte_engine.benchmark.source_binding import SOURCE_BINDING_REVISION
from mte_engine.benchmark.gate import evaluate_release_gate, load_policy
from mte_engine.benchmark.metrics import cer, pairwise_order_accuracy, wer
from mte_engine.benchmark.report_builder import build_report
from mte_engine.benchmark.selection import select_winners
from mte_engine.config import EngineSettings
from mte_engine.profile import current_profile_fingerprint, profile_state


def _write_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return sha256_path(path)

def _materialize_json(path: Path, value: object) -> Path:
    _write_json(path, value)
    return path


def _make_production_corpus(root: Path) -> tuple[Path, dict]:
    pages_dir = root / "pages"
    annotations_dir = root / "annotations"
    clean_dir = root / "clean"
    pages_dir.mkdir(parents=True)
    annotations_dir.mkdir(parents=True)
    clean_dir.mkdir(parents=True)
    languages = ["en"] * 60 + ["ja"] * 10 + ["ko"] * 10 + ["zh-Hans"] * 5 + ["zh-Hant"] * 5
    required_features = [
        "black-and-white", "color", "small-text", "complex-background", "sfx-near-artwork",
        "long-webtoon-slice", "arabic-target-rendering",
    ]
    pages = []
    page_ids = [f"p{i:03d}" for i in range(len(languages))]
    review = {
        "schemaVersion": 1,
        "reviewRecordId": "unit-test-rights-review",
        "sourceId": "operator-owned-or-explicitly-permissioned",
        "sourceRevision": "unit-test-rights-v1",
        "reviewer": "unit-test",
        "reviewedAtUtc": "2026-08-19T00:00:00Z",
        "benchmarkUseAuthorized": True,
        "commercialV1QualificationAuthorized": True,
        "redistributionAuthorized": False,
        "coverageMode": "page-list",
        "pageIds": page_ids,
        "evidence": [{"kind": "owned-test-fixture", "ref": "unit-test/generated-owned-fixture"}],
    }
    review_path = root / "rights" / "reviews" / "unit-test-rights-review.json"
    review_sha = _write_json(review_path, review)
    sfx_indices = {0, 1, 2, 3, 4, 5, 60, 70, 80, 85}
    for i, language in enumerate(languages):
        page_id = f"p{i:03d}"
        image_path = pages_dir / f"{page_id}.png"
        Image.new("RGB", (16, 16), ((i * 31) % 256, (i * 67) % 256, (i * 97) % 256)).save(image_path)
        blocks = [{
            "blockId": "d1", "kind": "dialogue", "polygon": [[1, 1], [8, 1], [8, 8], [1, 8]],
            "text": "HELLO", "readingOrder": 0,
        }]
        if i in sfx_indices:
            blocks.append({
                "blockId": "s1", "kind": "sfx", "polygon": [[9, 9], [14, 9], [14, 14], [9, 14]],
                "text": "BOOM", "readingOrder": 1,
            })
        annotation_path = annotations_dir / f"{page_id}.json"
        annotation_sha = _write_json(annotation_path, {"schemaVersion": 1, "blocks": blocks})
        page = {
            "pageId": page_id,
            "language": language,
            "imagePath": image_path.relative_to(root).as_posix(),
            "imageSha256": sha256_path(image_path),
            "annotationPath": annotation_path.relative_to(root).as_posix(),
            "annotationSha256": annotation_sha,
            "features": (
                required_features + ["english-uppercase-or-italic-or-outline"] if i == 0
                else ["vertical-japanese", "furigana"] if i == 60
                else []
            ),
            "rights": {
                "reviewed": True,
                "benchmarkUseAuthorized": True,
                "basis": "test-generated-owned-fixture",
                "source": "unit-test",
                "redistributionAuthorized": False,
                "reviewRecordId": "unit-test-rights-review",
                "reviewedBy": "unit-test",
                "reviewedAtUtc": "2026-08-19T00:00:00Z",
                "evidenceRef": "unit-test/generated-owned-fixture",
                "sourceId": "operator-owned-or-explicitly-permissioned",
                "sourceRevision": "unit-test-rights-v1",
                "reviewRecordPath": review_path.relative_to(root).as_posix(),
                "reviewRecordSha256": review_sha,
            },
        }
        if i < 5:
            clean_path = clean_dir / f"{page_id}.png"
            Image.new("RGB", (16, 16), (255, 255 - i, 255)).save(clean_path)
            page["cleanReferencePath"] = clean_path.relative_to(root).as_posix()
            page["cleanReferenceSha256"] = sha256_path(clean_path)
        pages.append(page)
    registry = load_source_registry()
    manifest = {
        "schemaVersion": 2,
        "policyRevision": "rev10-production-corpus-v2",
        "sourceRegistryRevision": registry["registryRevision"],
        "sourceRegistrySha256": source_registry_digest(registry),
        "corpusId": "synthetic-owned-production-shape-fixture",
        "pages": pages,
    }
    path = root / "corpus-manifest.json"
    _write_json(path, manifest)
    return path, manifest


def _candidate(candidate_id: str, component: str, family: str, artifact: str, metrics: dict, *, policy_role: str | None = None) -> dict:
    value = {
        "candidateId": candidate_id,
        "component": component,
        "family": family,
        "artifactIds": [artifact],
        "metrics": metrics,
    }
    if policy_role:
        value["policyRole"] = policy_role
    return value


def _make_catalog(root: Path, *, include_unresolved: bool = True, font_source: Path | None = None) -> tuple[Path, Path, list[dict]]:
    artifacts_dir = root / "model-artifacts"
    artifacts_dir.mkdir(parents=True)
    specs = [
        ("det-comic", "det-comic.bin", "detector"),
        ("det-pp", "det-pp.bin", "detector"),
        ("en-small", "en-small.bin", "ocr"),
        ("en-medium", "en-medium.bin", "ocr"),
        ("ja-manga", "ja-manga.bin", "ocr"),
        ("ja-pp", "ja-pp.bin", "ocr"),
        ("ko", "ko.bin", "ocr"),
        ("zh-small", "zh-small.bin", "ocr"),
        ("zh-medium", "zh-medium.bin", "ocr"),
        ("lama", "lama.bin", "inpaint"),
        ("aot", "aot.bin", "inpaint"),
        ("font-art", "font.ttf", "font"),
    ]
    entries = []
    for index, (artifact_id, filename, kind) in enumerate(specs):
        artifact_path = artifacts_dir / filename
        if artifact_id == "font-art" and font_source is not None:
            artifact_path.write_bytes(font_source.read_bytes())
        else:
            artifact_path.write_bytes((artifact_id + str(index)).encode() * 7)
        entries.append({
            "artifactId": artifact_id,
            "kind": kind,
            "upstreamProject": "owned-test",
            "upstreamRevision": "v1",
            "sourceUrl": "https://example.invalid/owned-test",
            "expectedFilename": filename,
            "sha256": sha256_path(artifact_path),
            "codeLicense": "MIT",
            "benchmarkUseStatus": "approved",
            "artifactLicenseStatus": "approved",
            "redistributionStatus": "local-only",
            "provenanceNotes": "Synthetic unit-test artifact.",
        })
    if include_unresolved:
        entries.append({
            "artifactId": "unselected-research-candidate",
            "kind": "detector",
            "upstreamProject": "research-only",
            "upstreamRevision": "unresolved",
            "sourceUrl": "https://example.invalid/research-only",
            "expectedFilename": "not-downloaded.bin",
            "sha256": None,
            "codeLicense": "UNKNOWN",
            "benchmarkUseStatus": "pending",
            "artifactLicenseStatus": "pending",
            "redistributionStatus": "blocked",
            "provenanceNotes": "Unselected unresolved candidate must not block a release that did not benchmark or select it.",
        })
    catalog = {"schemaVersion": 1, "catalogRevision": "test-v1", "artifacts": entries}
    path = root / "catalog.json"
    _write_json(path, catalog)
    return path, artifacts_dir, entries


def _candidates() -> list[dict]:
    return [
        _candidate("det-good", "detector", "ppocrv6-small", "det-comic", {"dialogueRecall": 0.985, "precision": 0.95, "f1": 0.967, "criticalFalseEraseCount": 0, "artworkFalsePositiveAreaRate": 0.001, "p95Ms": 110, "peakMemoryMiB": 300}),
        _candidate("det-pp", "detector", "ppocrv6-medium", "det-pp", {"dialogueRecall": 0.975, "precision": 0.93, "f1": 0.952, "criticalFalseEraseCount": 0, "artworkFalsePositiveAreaRate": 0.002, "p95Ms": 140, "peakMemoryMiB": 360}),
        _candidate("en-good", "ocr-en", "ppocrv6-small", "en-small", {"cer": 0.035, "p95Ms": 80, "modelBytes": 20_000_000}),
        _candidate("en-medium", "ocr-en", "ppocrv6-medium", "en-medium", {"cer": 0.031, "p95Ms": 100, "modelBytes": 73_000_000}),
        _candidate("ja-manga", "ocr-ja", "manga-ocr", "ja-manga", {"cer": 0.07, "p95Ms": 130, "modelBytes": 400_000_000}),
        _candidate("ja-pp", "ocr-ja", "ppocrv6", "ja-pp", {"cer": 0.065, "p95Ms": 95, "modelBytes": 73_000_000}),
        _candidate("ko-good", "ocr-ko", "korean-ppocrv5", "ko", {"cer": 0.06, "p95Ms": 70, "modelBytes": 14_000_000}),
        _candidate("zh-good", "ocr-zh", "ppocrv6-small", "zh-small", {"cer": 0.05, "p95Ms": 85, "modelBytes": 20_000_000}),
        _candidate("zh-medium", "ocr-zh", "ppocrv6-medium", "zh-medium", {"cer": 0.047, "p95Ms": 110, "modelBytes": 73_000_000}),
        _candidate("inp-good", "inpaint", "lama", "lama", {"humanCriticalFailures": 0, "humanScore": 4.5, "p95Ms": 220, "peakMemoryMiB": 700}),
        _candidate("inp-aot", "inpaint", "aot", "aot", {"humanCriticalFailures": 0, "humanScore": 4.2, "p95Ms": 190, "peakMemoryMiB": 620}),
    ]


def _raw_report(manifest: dict, policy: dict) -> dict:
    ocr_rows = []
    samples = {"en": 55, "ja": 12, "ko": 12, "zh-Hans": 6, "zh-Hant": 6}
    texts = {
        "en": ("hello friend", "hello friend"),
        "ja": ("今日は", "今日は"),
        "ko": ("안녕하세요", "안녕하세요"),
        "zh-Hans": ("你好世界", "你好世界"),
        "zh-Hant": ("你好世界", "你好世界"),
    }
    for language, count in samples.items():
        reference, prediction = texts[language]
        for _ in range(count):
            ocr_rows.append({"language": language, "reference": reference, "prediction": prediction})
    detection_by_language = {
        language: {
            "truePositive": 98,
            "falsePositive": 3,
            "falseNegative": 2,
            "falseEraseCandidateCount": 0,
            "criticalFalseEraseCount": 0,
            "artworkFalsePositiveArea": 10,
            "artworkArea": 20000,
            "maskOverreachPixels": 10,
            "maskUndercoveragePixels": 10,
            "groundTruthTextPixels": 2000,
        }
        for language in ("en", "ja", "ko", "zh-Hans", "zh-Hant")
    }
    reading_counts = {"en": 22, "ja": 10, "ko": 10, "zh-Hans": 5, "zh-Hant": 5}
    reading_rows = [
        {"language": language, "reference": ["a", "b", "c"], "prediction": ["a", "b", "c"]}
        for language, count in reading_counts.items() for _ in range(count)
    ]
    return {
        "schemaVersion": 1,
        "reportId": "report-test-v1",
        "corpusId": manifest["corpusId"],
        "corpusManifestSha256": sha256_bytes(canonical_json(manifest)),
        "runtime": {
            "pythonVersion": "3.13.7",
            "os": "test-os",
            "cpu": "test-cpu",
            "gpu": "none",
            "hardwareClass": "cpu-mainstream-test",
            "paddlePaddleVersion": "3.2.2-test",
            "paddleOcrVersion": "3.7.0-test",
            "mangaOcrVersion": "0.1.16-test",
            "torchVersion": "2.x-test",
            "pillowVersion": "12.3.0-test"
        },
        "candidates": _candidates(),
        "detection": {
            "truePositive": 990,
            "falsePositive": 20,
            "falseNegative": 10,
            "falseEraseCandidateCount": 0,
            "criticalFalseEraseCount": 0,
            "artworkFalsePositiveArea": 100,
            "artworkArea": 100000,
            "maskOverreachPixels": 100,
            "maskUndercoveragePixels": 100,
            "groundTruthTextPixels": 10000,
        },
        "detectionByLanguage": detection_by_language,
        "ocrRows": ocr_rows,
        "readingOrderRows": reading_rows,
        "sfxRows": [
            {
                "pageId": page["pageId"],
                "blockId": "s1",
                "language": page["language"],
                "groundTruthKind": "sfx",
                "groundTruthPixels": 500,
                "protectedFromEditing": True,
                "sentToTranslator": False,
                "eraseInpaintOverlapPixels": 0,
                "changedPixelsAfterEncodeDecode": 0,
                "destructiveEditPixels": 0,
                "protectedConflictSilentOverwrite": False,
            }
            for page in manifest["pages"]
            if page["pageId"] in {"p000", "p001", "p002", "p003", "p004", "p005", "p060", "p070", "p080", "p085"}
        ],
        "qualityExtra": {
            "arabicRendererGoldensRun": 24,
            "arabicRendererGoldensFailed": 0,
            "inpainting": {"cleanReferencePages": 5, "mae": 2.1, "psnrMean": 34.0},
        },
        "humanReview": {
            "translationPagesReviewed": 35,
            "translationPagesByLanguage": {"en": 22, "ja": 4, "ko": 4, "zh-Hans": 3, "zh-Hant": 2},
            "inpaintingPagesReviewed": 25,
            "criticalTranslationFailures": 0,
            "criticalInpaintingFailures": 0,
            "arabicNaturalnessMean": 4.4,
        },
        "translation": {
            "adapterId": "page-context-translator-v1",
            "modelOrProviderRevision": "owned-test-translator-v1",
            "contextMode": "page-block-batch",
            "privacyMode": "explicit-config-no-sfx",
            "roleClassifierRevision": "visual-enclosure-sfx-guard-v1",
        },
        "renderer": {
            "adapterRevision": "pillow-raqm-ar-v1",
            "fontArtifactId": "font-art",
            "goldenSuiteRevision": "arabic-goldens-v1"
        },
        "performance": {
            "pageSeconds": [1.0 + (i % 7) * 0.03 for i in range(90)],
            "peakRamMiB": 1024,
            "peakVramMiB": 0,
            "modelLoadSeconds": 2.0,
            "stageMs": {"ocr": {"p50": 90, "p95": 130}},
            "resultBytes": {"mean": 1200000, "p95": 1800000},
        },
    }


def _test_dependency_locks() -> dict:
    return {
        "revision": "rev11-qualification-dependency-lock-pins-v1",
        "packageLockSha256": "sha256:" + "d" * 64,
        "uvLockSha256": "sha256:" + "c" * 64,
        "npmPackageCount": 2,
        "uvPackageCount": 2,
    }




def _test_qualified_source() -> dict:
    return {
        "revision": SOURCE_BINDING_REVISION,
        "sourceHeadSha": "a" * 40,
        "runtimeTrees": {
            "src": {"fileCount": 1, "treeSha256": "sha256:" + "1" * 64},
            "engine/mte_engine": {"fileCount": 1, "treeSha256": "sha256:" + "2" * 64},
        },
    }


def _prepare_freeze_inputs(gate: dict, report: dict) -> None:
    gate["dependencyLocks"] = _test_dependency_locks()
    gate["candidatePlanSha256"] = "sha256:" + "b" * 64
    gate["runPlanSha256"] = "sha256:" + "e" * 64
    report["execution"] = {"executorSourceSha256": "sha256:" + "f" * 64}

def _policy_path() -> Path:
    return Path(__file__).resolve().parents[1] / "benchmark" / "policies" / "benchmark-thresholds-v3.json"


def test_text_metrics_and_order_are_deterministic():
    assert cer("abc", "abc") == 0
    assert cer("abc", "axc") == pytest.approx(1 / 3)
    assert wer("hello world", "hello there") == pytest.approx(0.5)
    assert pairwise_order_accuracy(["a", "b", "c"], ["a", "b", "c"]) == 1.0
    assert pairwise_order_accuracy(["a", "b", "c"], ["b", "a", "c"]) == pytest.approx(2 / 3)


def test_corpus_gate_requires_rev10_language_and_visual_coverage(tmp_path: Path):
    path, manifest = _make_production_corpus(tmp_path)
    loaded = load_corpus(path)
    summary = validate_corpus(loaded, base_dir=tmp_path)
    passed, reasons = production_corpus_gate(summary)
    assert passed and not reasons
    assert summary["languageCounts"] == {"en": 60, "ja": 10, "ko": 10, "zh-Hans": 5, "zh-Hant": 5}
    assert summary["groundTruthSfxPages"] == 10


def test_corpus_rejects_unreviewed_rights_and_duplicate_pages(tmp_path: Path):
    path, manifest = _make_production_corpus(tmp_path)
    manifest["pages"][0]["rights"]["reviewed"] = False
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(CorpusError, match="rights.reviewed"):
        load_corpus(path)

    path, manifest = _make_production_corpus(tmp_path / "dup")
    manifest["pages"][1]["imageSha256"] = manifest["pages"][0]["imageSha256"]
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(CorpusError, match="duplicate imageSha256"):
        load_corpus(path)



def test_corpus_paths_cannot_escape_or_use_symlink(tmp_path: Path):
    path, manifest = _make_production_corpus(tmp_path / "corpus")
    manifest["pages"][0]["imagePath"] = "../outside.png"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(CorpusError, match="stay inside"):
        load_corpus(path)

    path, manifest = _make_production_corpus(tmp_path / "symlink")
    original = (path.parent / manifest["pages"][0]["imagePath"]).resolve()
    link = path.parent / "pages" / "linked.png"
    try:
        link.symlink_to(original)
    except OSError:
        pytest.skip("symlink creation unavailable")
    manifest["pages"][0]["imagePath"] = link.relative_to(path.parent).as_posix()
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(CorpusError, match="symlink"):
        load_corpus(path)


def test_catalog_rejects_path_traversal_and_non_https_sources(tmp_path: Path):
    catalog_path, _, _ = _make_catalog(tmp_path, include_unresolved=False)
    catalog = json.loads(catalog_path.read_text())
    catalog["artifacts"][0]["expectedFilename"] = "../escape.bin"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    with pytest.raises(CatalogError, match="safe relative path"):
        load_catalog(catalog_path)
    catalog["artifacts"][0]["expectedFilename"] = "det.bin"
    catalog["artifacts"][0]["sourceUrl"] = "http://example.invalid/model"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    with pytest.raises(CatalogError, match="HTTPS"):
        load_catalog(catalog_path)


def test_catalog_requires_real_local_digest_when_release_gate_requests_it(tmp_path: Path):
    catalog_path, artifacts_dir, entries = _make_catalog(tmp_path, include_unresolved=False)
    load_catalog(catalog_path, artifacts_dir=artifacts_dir, require_local_hashes=True)
    (artifacts_dir / entries[0]["expectedFilename"]).write_bytes(b"tampered")
    with pytest.raises(CatalogError, match="digest mismatch"):
        load_catalog(catalog_path, artifacts_dir=artifacts_dir, require_local_hashes=True)


def test_selection_uses_same_quality_rule_for_japanese_and_rejects_unsafe_detector():
    policy = load_policy(_policy_path())
    candidates = _candidates() + [
        _candidate("det-unsafe", "detector", "ppocrv6-small", "det-comic", {"dialogueRecall": 0.999, "precision": 0.999, "f1": 0.999, "criticalFalseEraseCount": 1, "artworkFalsePositiveAreaRate": 0.0, "p95Ms": 10, "peakMemoryMiB": 10}),
        _candidate("ja-pp-better", "ocr-ja", "ppocrv6", "ja-pp", {"cer": 0.01, "p95Ms": 50, "modelBytes": 20_000_000}),
    ]
    selected = select_winners(candidates, policy)
    assert selected["detector"] == "det-good"
    assert selected["ocrJapanese"] == "ja-pp-better"


def test_small_ocr_only_wins_when_quality_is_near_and_latency_materially_better():
    policy = load_policy(_policy_path())
    base = [c for c in _candidates() if c["component"] != "ocr-en"]
    base += [
        _candidate("en-medium", "ocr-en", "ppocrv6-medium", "en-medium", {"cer": 0.030, "p95Ms": 100, "modelBytes": 73_000_000}),
        _candidate("en-small", "ocr-en", "ppocrv6-small", "en-small", {"cer": 0.034, "p95Ms": 70, "modelBytes": 20_000_000}),
    ]
    assert select_winners(base, policy)["ocrEnglish"] == "en-small"
    base[-1]["metrics"]["cer"] = 0.040
    assert select_winners(base, policy)["ocrEnglish"] == "en-medium"


def test_raw_report_recomputes_metrics_and_selected_candidates(tmp_path: Path):
    _, manifest = _make_production_corpus(tmp_path)
    policy = load_policy(_policy_path())
    raw = _raw_report(manifest, policy)
    report = build_report(raw, policy)
    assert report["selected"]["detector"] == "det-good"
    assert report["quality"]["ocr"]["en"]["cer"] == 0
    assert report["sfxSafety"]["changedPixelRateAfterEncodeDecode"] == 0
    assert report["performance"]["p95PageSeconds"] == pytest.approx(1.18)


def test_role_classifier_requires_perfect_sfx_recall_and_exact_production_revision(tmp_path: Path):
    corpus_path, manifest = _make_production_corpus(tmp_path / "corpus")
    policy_path = _policy_path()
    policy = load_policy(policy_path)
    raw = _raw_report(manifest, policy)
    raw["sfxRows"][0]["protectedFromEditing"] = False
    raw["translation"]["roleClassifierRevision"] = "visual-enclosure-sfx-guard-v1"
    report = build_report(raw, policy)
    report_path = tmp_path / "report.json"
    _write_json(report_path, report)
    catalog_path, artifacts_dir, _ = _make_catalog(tmp_path / "catalog")
    gate = evaluate_release_gate(corpus_path=corpus_path, raw_path=_materialize_json(tmp_path / "raw.json", raw), report_path=report_path, policy_path=policy_path, catalog_path=catalog_path, artifacts_dir=artifacts_dir)
    assert gate["passed"] is False
    assert any("protected recall" in reason for reason in gate["reasons"])

    raw = _raw_report(manifest, policy)
    raw["translation"]["roleClassifierRevision"] = "unreviewed-role-v2"
    report = build_report(raw, policy)
    _write_json(report_path, report)
    gate = evaluate_release_gate(corpus_path=corpus_path, raw_path=_materialize_json(tmp_path / "raw.json", raw), report_path=report_path, policy_path=policy_path, catalog_path=catalog_path, artifacts_dir=artifacts_dir)
    assert gate["passed"] is False
    assert any("classifier revision" in reason for reason in gate["reasons"])



def test_sfx_raw_evidence_must_exactly_cover_corpus_annotations(tmp_path: Path):
    corpus_path, manifest = _make_production_corpus(tmp_path / "corpus")
    policy_path = _policy_path()
    policy = load_policy(policy_path)
    raw = _raw_report(manifest, policy)
    raw["sfxRows"].pop()
    report = build_report(raw, policy)
    report_path = tmp_path / "report.json"
    _write_json(report_path, report)
    catalog_path, artifacts_dir, _ = _make_catalog(tmp_path / "catalog")
    gate = evaluate_release_gate(
        corpus_path=corpus_path,
        raw_path=_materialize_json(tmp_path / "raw.json", raw),
        report_path=report_path,
        policy_path=policy_path,
        catalog_path=catalog_path,
        artifacts_dir=artifacts_dir,
    )
    assert gate["passed"] is False
    assert any("exactly cover corpus ground-truth SFX blocks" in reason for reason in gate["reasons"])


def test_sfx_raw_evidence_rejects_duplicate_block_rows(tmp_path: Path):
    _, manifest = _make_production_corpus(tmp_path / "corpus")
    policy = load_policy(_policy_path())
    raw = _raw_report(manifest, policy)
    raw["sfxRows"].append(dict(raw["sfxRows"][0]))
    with pytest.raises(ValueError, match="duplicate pageId/blockId"):
        build_report(raw, policy)


def test_gate_rebuilds_report_from_raw_and_rejects_manual_green_edits(tmp_path: Path):
    corpus_path, manifest = _make_production_corpus(tmp_path / "corpus")
    policy_path = _policy_path()
    policy = load_policy(policy_path)
    raw = _raw_report(manifest, policy)
    raw["sfxRows"][0]["sentToTranslator"] = True
    report = build_report(raw, policy)
    # Simulate a hand-edited report that hides the destructive event.
    report["sfxSafety"]["sentToTranslatorRate"] = 0.0
    report_path = tmp_path / "report.json"
    _write_json(report_path, report)
    catalog_path, artifacts_dir, _ = _make_catalog(tmp_path / "catalog")
    gate = evaluate_release_gate(
        corpus_path=corpus_path,
        raw_path=_materialize_json(tmp_path / "raw.json", raw),
        report_path=report_path,
        policy_path=policy_path,
        catalog_path=catalog_path,
        artifacts_dir=artifacts_dir,
    )
    assert gate["passed"] is False
    assert any("deterministic rebuild" in reason for reason in gate["reasons"])

def test_complete_release_gate_can_pass_only_with_real_corpus_files_and_artifact_pins(tmp_path: Path):
    corpus_path, manifest = _make_production_corpus(tmp_path / "corpus")
    policy_path = _policy_path()
    policy = load_policy(policy_path)
    raw = _raw_report(manifest, policy)
    report = build_report(raw, policy)
    report_path = tmp_path / "report.json"
    _write_json(report_path, report)
    catalog_path, artifacts_dir, _ = _make_catalog(tmp_path / "catalog")
    gate = evaluate_release_gate(
        corpus_path=corpus_path,
        raw_path=_materialize_json(tmp_path / "raw.json", raw),
        report_path=report_path,
        policy_path=policy_path,
        catalog_path=catalog_path,
        artifacts_dir=artifacts_dir,
    )
    assert gate["passed"] is True
    assert len(gate["selectedArtifacts"]) == 7



def test_unselected_unresolved_catalog_candidate_does_not_block_selected_release(tmp_path: Path):
    corpus_path, manifest = _make_production_corpus(tmp_path / "corpus")
    policy_path = _policy_path()
    policy = load_policy(policy_path)
    raw = _raw_report(manifest, policy)
    report = build_report(raw, policy)
    report_path = tmp_path / "report.json"
    _write_json(report_path, report)
    catalog_path, artifacts_dir, entries = _make_catalog(tmp_path / "catalog")
    assert any(item["artifactId"] == "unselected-research-candidate" and item["sha256"] is None for item in entries)
    gate = evaluate_release_gate(corpus_path=corpus_path, raw_path=_materialize_json(tmp_path / "raw.json", raw), report_path=report_path, policy_path=policy_path, catalog_path=catalog_path, artifacts_dir=artifacts_dir)
    assert gate["passed"] is True


def test_any_nonzero_sfx_metric_blocks_freeze(tmp_path: Path):
    corpus_path, manifest = _make_production_corpus(tmp_path / "corpus")
    policy_path = _policy_path()
    policy = load_policy(policy_path)
    raw = _raw_report(manifest, policy)
    report = build_report(raw, policy)
    report["sfxSafety"]["changedPixelRateAfterEncodeDecode"] = 1 / 5000
    report_path = tmp_path / "report.json"
    _write_json(report_path, report)
    catalog_path, artifacts_dir, _ = _make_catalog(tmp_path / "catalog")
    gate = evaluate_release_gate(corpus_path=corpus_path, raw_path=_materialize_json(tmp_path / "raw.json", raw), report_path=report_path, policy_path=policy_path, catalog_path=catalog_path, artifacts_dir=artifacts_dir)
    assert gate["passed"] is False
    assert any("exact zero" in reason for reason in gate["reasons"])


def test_report_cannot_override_deterministic_winner(tmp_path: Path):
    corpus_path, manifest = _make_production_corpus(tmp_path / "corpus")
    policy_path = _policy_path()
    policy = load_policy(policy_path)
    raw = _raw_report(manifest, policy)
    report = build_report(raw, policy)
    report["selected"]["detector"] = "made-up"
    report_path = tmp_path / "report.json"
    _write_json(report_path, report)
    catalog_path, artifacts_dir, _ = _make_catalog(tmp_path / "catalog")
    gate = evaluate_release_gate(corpus_path=corpus_path, raw_path=_materialize_json(tmp_path / "raw.json", raw), report_path=report_path, policy_path=policy_path, catalog_path=catalog_path, artifacts_dir=artifacts_dir)
    assert gate["passed"] is False
    assert any("deterministic selection" in reason for reason in gate["reasons"])


def test_release_gate_requires_full_candidate_comparison_matrix(tmp_path: Path):
    corpus_path, manifest = _make_production_corpus(tmp_path / "corpus")
    policy_path = _policy_path()
    policy = load_policy(policy_path)
    raw = _raw_report(manifest, policy)
    raw["candidates"] = [c for c in raw["candidates"] if c["family"] != "aot"]
    report = build_report(raw, policy)
    report_path = tmp_path / "report.json"
    _write_json(report_path, report)
    catalog_path, artifacts_dir, _ = _make_catalog(tmp_path / "catalog")
    gate = evaluate_release_gate(corpus_path=corpus_path, raw_path=_materialize_json(tmp_path / "raw.json", raw), report_path=report_path, policy_path=policy_path, catalog_path=catalog_path, artifacts_dir=artifacts_dir)
    assert gate["passed"] is False
    assert any("candidate coverage is incomplete for inpaint" in reason for reason in gate["reasons"])


def test_benchmarked_loser_still_needs_approved_use_and_real_hash(tmp_path: Path):
    corpus_path, manifest = _make_production_corpus(tmp_path / "corpus")
    policy_path = _policy_path()
    policy = load_policy(policy_path)
    raw = _raw_report(manifest, policy)
    report = build_report(raw, policy)
    report_path = tmp_path / "report.json"
    _write_json(report_path, report)
    catalog_path, artifacts_dir, _ = _make_catalog(tmp_path / "catalog")
    catalog = json.loads(catalog_path.read_text())
    loser = next(item for item in catalog["artifacts"] if item["artifactId"] == "aot")
    loser["benchmarkUseStatus"] = "pending"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    gate = evaluate_release_gate(corpus_path=corpus_path, raw_path=_materialize_json(tmp_path / "raw.json", raw), report_path=report_path, policy_path=policy_path, catalog_path=catalog_path, artifacts_dir=artifacts_dir)
    assert gate["passed"] is False
    assert any("benchmark use is not approved for artifact: aot" in reason for reason in gate["reasons"])


def test_catalog_refuses_nested_symlink_artifact_path(tmp_path: Path):
    catalog_path, artifacts_dir, entries = _make_catalog(tmp_path / "catalog", include_unresolved=False)
    nested = artifacts_dir / "nested"
    nested.mkdir()
    real = artifacts_dir / "real"
    real.mkdir()
    target = real / "model.bin"
    target.write_bytes(b"safe-model")
    link = nested / "linked"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    catalog = json.loads(catalog_path.read_text())
    catalog["artifacts"][0]["expectedFilename"] = "nested/linked/model.bin"
    catalog["artifacts"][0]["sha256"] = sha256_path(target)
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    with pytest.raises(CatalogError, match="symlink"):
        load_catalog(catalog_path, artifacts_dir=artifacts_dir)


def test_language_specific_quality_deficit_blocks_gate(tmp_path: Path):
    corpus_path, manifest = _make_production_corpus(tmp_path / "corpus")
    policy_path = _policy_path()
    policy = load_policy(policy_path)
    raw = _raw_report(manifest, policy)
    report = build_report(raw, policy)
    report["quality"]["detectionByLanguage"]["ja"]["dialogueRecall"] = 0.5
    report_path = tmp_path / "report.json"
    _write_json(report_path, report)
    catalog_path, artifacts_dir, _ = _make_catalog(tmp_path / "catalog")
    gate = evaluate_release_gate(corpus_path=corpus_path, raw_path=_materialize_json(tmp_path / "raw.json", raw), report_path=report_path, policy_path=policy_path, catalog_path=catalog_path, artifacts_dir=artifacts_dir)
    assert gate["passed"] is False
    assert any("recall is below release policy for ja" in reason for reason in gate["reasons"])


def test_nonfinite_report_number_is_rejected_before_threshold_evaluation(tmp_path: Path):
    _, manifest = _make_production_corpus(tmp_path / "corpus")
    policy = load_policy(_policy_path())
    raw = _raw_report(manifest, policy)
    report = build_report(raw, policy)
    report["performance"]["peakRamMiB"] = float("nan")
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report, allow_nan=True), encoding="utf-8")
    from mte_engine.benchmark.gate import BenchmarkGateError, load_report
    with pytest.raises(BenchmarkGateError, match="non-finite"):
        load_report(report_path)


def test_freeze_is_content_addressed_and_tamper_evident(tmp_path: Path):
    corpus_path, manifest = _make_production_corpus(tmp_path / "corpus")
    policy_path = _policy_path()
    policy = load_policy(policy_path)
    raw = _raw_report(manifest, policy)
    report = build_report(raw, policy)
    report_path = tmp_path / "report.json"
    _write_json(report_path, report)
    catalog_path, artifacts_dir, _ = _make_catalog(tmp_path / "catalog")
    gate = evaluate_release_gate(corpus_path=corpus_path, raw_path=_materialize_json(tmp_path / "raw.json", raw), report_path=report_path, policy_path=policy_path, catalog_path=catalog_path, artifacts_dir=artifacts_dir)
    _prepare_freeze_inputs(gate, report)
    freeze = build_freeze(gate=gate, report=report, corpus_manifest_sha256=sha256_bytes(canonical_json(manifest)), qualified_source=_test_qualified_source())
    assert validate_freeze(freeze)
    assert freeze["policyRevision"] == "benchmark-thresholds-v3"
    assert freeze["roleSafetyQualification"]["roleClassifierSfxProtectedRecall"] == 1.0
    assert freeze["roleSafetyQualification"]["sentToTranslatorRate"] == 0.0
    assert freeze["inpaintingQualification"]["candidateId"] == freeze["selected"]["inpainter"]
    assert freeze["inpaintingQualification"]["humanScore"] >= 4.0
    semantic_tamper = json.loads(json.dumps(freeze))
    semantic_tamper["roleSafetyQualification"]["roleClassifierSfxProtectedRecall"] = 0.99
    semantic_body = dict(semantic_tamper)
    semantic_body.pop("freezeSha256", None)
    semantic_tamper["freezeSha256"] = sha256_bytes(canonical_json(semantic_body))
    assert not validate_freeze(semantic_tamper)
    freeze_path = tmp_path / "freeze.json"
    _write_json(freeze_path, freeze)
    assert load_freeze(freeze_path) is not None
    freeze["runtime"]["cpu"] = "tampered"
    _write_json(freeze_path, freeze)
    assert load_freeze(freeze_path) is None


def test_frozen_renderer_font_digest_is_enforced(tmp_path: Path):
    font = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    alternate = Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf")
    if not font.is_file() or not alternate.is_file():
        pytest.skip("test fonts unavailable")
    corpus_path, manifest = _make_production_corpus(tmp_path / "corpus")
    policy_path = _policy_path()
    policy = load_policy(policy_path)
    raw = _raw_report(manifest, policy)
    report = build_report(raw, policy)
    report_path = tmp_path / "report.json"
    _write_json(report_path, report)
    catalog_path, artifacts_dir, _ = _make_catalog(tmp_path / "catalog", font_source=font)
    gate = evaluate_release_gate(corpus_path=corpus_path, raw_path=_materialize_json(tmp_path / "raw.json", raw), report_path=report_path, policy_path=policy_path, catalog_path=catalog_path, artifacts_dir=artifacts_dir)
    _prepare_freeze_inputs(gate, report)
    freeze = build_freeze(gate=gate, report=report, corpus_manifest_sha256=sha256_bytes(canonical_json(manifest)), qualified_source=_test_qualified_source())
    freeze_path = tmp_path / "freeze.json"
    _write_json(freeze_path, freeze)
    settings = EngineSettings(
        data_dir=tmp_path / "data",
        arabic_font_path=alternate,
        production_freeze_path=freeze_path,
        model_artifacts_dir=artifacts_dir,
    )
    assert profile_state("default-v1", settings) == "renderer-missing"


def test_default_profile_fingerprint_changes_after_valid_freeze_and_stays_blocked_until_runtime_wiring(tmp_path: Path):
    font = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    if not font.is_file():
        pytest.skip("test font unavailable")
    pending = current_profile_fingerprint(font_path=font, freeze_path=tmp_path / "missing.json")

    corpus_path, manifest = _make_production_corpus(tmp_path / "corpus")
    policy_path = _policy_path()
    policy = load_policy(policy_path)
    raw = _raw_report(manifest, policy)
    report = build_report(raw, policy)
    report_path = tmp_path / "report.json"
    _write_json(report_path, report)
    catalog_path, artifacts_dir, _ = _make_catalog(tmp_path / "catalog", font_source=font)
    gate = evaluate_release_gate(corpus_path=corpus_path, raw_path=_materialize_json(tmp_path / "raw.json", raw), report_path=report_path, policy_path=policy_path, catalog_path=catalog_path, artifacts_dir=artifacts_dir)
    _prepare_freeze_inputs(gate, report)
    freeze = build_freeze(gate=gate, report=report, corpus_manifest_sha256=sha256_bytes(canonical_json(manifest)), qualified_source=_test_qualified_source())
    freeze_path = tmp_path / "freeze.json"
    _write_json(freeze_path, freeze)
    frozen = current_profile_fingerprint(font_path=font, freeze_path=freeze_path)
    assert frozen != pending

    settings = EngineSettings(
        data_dir=tmp_path / "data",
        arabic_font_path=font,
        production_freeze_path=freeze_path,
        model_artifacts_dir=artifacts_dir,
    )
    assert profile_state("default-v1", settings) == "runtime-unavailable"
