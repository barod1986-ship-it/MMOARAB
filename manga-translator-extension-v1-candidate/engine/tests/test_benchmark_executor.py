from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

import mte_engine.benchmark.execution as execution
from mte_engine.benchmark.candidate_plan import candidate_plan_digest
from mte_engine.benchmark.common import canonical_json, sha256_bytes, sha256_file, sha256_path
from mte_engine.benchmark.corpus_sources import load_source_registry, source_registry_digest
from mte_engine.benchmark.execution import (
    BenchmarkExecutionError,
    executor_pin,
    seal_raw_execution,
    seal_review_draft,
    validate_raw_execution,
    verify_execution_inputs,
)
from mte_engine.benchmark.report_builder import build_report
from mte_engine.benchmark.run_plan import run_plan_digest


def _policy() -> dict:
    return {
        "schemaVersion": 1,
        "policyRevision": "executor-test-policy-v1",
        "candidateCoverage": {},
        "qualityThresholds": {
            "dialogueRecallMin": 0.5,
            "detectionPrecisionMin": 0.5,
            "artworkFalsePositiveAreaRateMax": 1.0,
            "ocrCerMax": {"en": 1.0, "ja": 1.0, "ko": 1.0, "zh-Hans": 1.0, "zh-Hant": 1.0},
            "inpaintingHumanScoreMin": 0.0,
        },
    }


def _schema2_raw() -> tuple[dict, dict]:
    plan = {
        "schemaVersion": 2,
        "runPlanRevision": "rev11-production-benchmark-run-plan-v3",
        "createdAtUtc": "2026-08-19T12:00:00Z",
        "ready": True,
        "reasons": [],
        "corpusId": "corpus-a",
        "corpusManifestSha256": "sha256:" + "1" * 64,
        "policyRevision": "policy-a",
        "policySha256": "sha256:" + "2" * 64,
        "catalogRevision": "catalog-a",
        "catalogSha256": "sha256:" + "3" * 64,
        "candidatePlanRevision": "candidate-a",
        "candidatePlanSha256": "sha256:" + "4" * 64,
        "executor": executor_pin(),
        "dependencyLocks": {"revision": "rev11-qualification-dependency-lock-pins-v1", "packageLockSha256": "sha256:" + "d" * 64, "uvLockSha256": "sha256:" + "c" * 64, "npmPackageCount": 2, "uvPackageCount": 2},
        "artifactPins": [
            {"artifactId": name, "sha256": "sha256:" + str(index) * 64, "expectedFilename": f"{name}.bin"}
            for index, name in enumerate(("det", "en", "ja", "ko", "zh", "inp"), 5)
        ],
        "artifactReceiptSha256s": {
            name: "sha256:" + "a" * 64 for name in ("det", "en", "ja", "ko", "zh", "inp")
        },
    }
    plan["runPlanSha256"] = run_plan_digest(plan)
    review = seal_review_draft({
        "schemaVersion": 1,
        "reviewRevision": "rev10-production-benchmark-review-v1",
        "reportId": "report-executor-test",
        "runPlanSha256": plan["runPlanSha256"],
        "inpaintingCandidates": {"inp-1": {"pagesReviewed": 20, "humanScore": 4.5, "criticalFailures": 0}},
        "translation": {
            "pagesReviewed": 30,
            "pagesByLanguage": {"en": 20, "ja": 3, "ko": 3, "zh-Hans": 2, "zh-Hant": 2},
            "criticalFailures": 0,
            "arabicNaturalnessMean": 4.5,
            "adapterId": "external-ocr-text-only-v1",
            "modelOrProviderRevision": "provider-test-v1",
            "contextMode": "page-block-batch",
            "privacyMode": "explicit-config-no-sfx",
        },
        "renderer": {
            "arabicRendererGoldensRun": 24,
            "arabicRendererGoldensFailed": 0,
            "adapterRevision": "pillow-raqm-ar-v1",
            "fontArtifactId": "font-test",
            "goldenSuiteRevision": "goldens-test-v1",
        },
    })
    candidates = [
        {"candidateId": "det-1", "component": "detector", "family": "det-family", "artifactIds": ["det"], "metrics": {"dialogueRecall": 0.0}},
        {"candidateId": "en-1", "component": "ocr-en", "family": "en-family", "artifactIds": ["en"], "metrics": {"cer": 1.0}},
        {"candidateId": "ja-1", "component": "ocr-ja", "family": "ja-family", "artifactIds": ["ja"], "policyRole": "primary", "metrics": {"cer": 1.0}},
        {"candidateId": "ko-1", "component": "ocr-ko", "family": "ko-family", "artifactIds": ["ko"], "metrics": {"cer": 1.0}},
        {"candidateId": "zh-1", "component": "ocr-zh", "family": "zh-family", "artifactIds": ["zh"], "metrics": {"cer": 1.0}},
        {"candidateId": "inp-1", "component": "inpaint", "family": "inp-family", "artifactIds": ["inp"], "metrics": {"humanScore": 0.0}},
    ]
    det_counts = {
        "truePositive": 10, "falsePositive": 0, "falseNegative": 0,
        "falseEraseCandidateCount": 0, "criticalFalseEraseCount": 0,
        "artworkFalsePositiveArea": 0, "artworkArea": 100,
        "maskOverreachPixels": 0, "maskUndercoveragePixels": 0, "groundTruthTextPixels": 100,
    }
    ocr = {}
    for candidate_id, language, text in (("en-1", "en", "hello"), ("ja-1", "ja", "今日は"), ("ko-1", "ko", "안녕"), ("zh-1", "zh-Hans", "你好")):
        ocr[candidate_id] = {"rows": [{"pageId": "p1", "blockId": "d1", "language": language, "reference": text, "prediction": text, "confidence": 1.0}], "durationsMs": [10.0], "modelBytes": 100}
    raw = {
        "schemaVersion": 2,
        "reportId": review["reportId"],
        "corpusId": plan["corpusId"],
        "corpusManifestSha256": plan["corpusManifestSha256"],
        "candidatePlanSha256": plan["candidatePlanSha256"],
        "runPlanSha256": plan["runPlanSha256"],
        "candidates": candidates,
        "execution": {
            "attestationRevision": "rev10-benchmark-execution-attestation-v1",
            "executorRevision": plan["executor"]["revision"],
            "executorSourceSha256": plan["executor"]["sourceSha256"],
            "runPlanSha256": plan["runPlanSha256"],
            "artifactSha256s": {item["artifactId"]: item["sha256"] for item in plan["artifactPins"]},
            "reviewRecordSha256": review["reviewRecordSha256"],
            "reviewSnapshot": review,
            "runtime": {key: "test" for key in ("pythonVersion", "os", "cpu", "gpu", "hardwareClass", "paddlePaddleVersion", "paddleOcrVersion", "mangaOcrVersion", "torchVersion", "pillowVersion")},
            "machineEvidence": {
                "detectorCandidates": {"det-1": {"aggregate": det_counts, "byLanguage": {"en": det_counts}, "pageRows": [{"pageId": "p1", "language": "en", "counts": det_counts, "predictedRegions": 10}], "durationsMs": [12.0]}},
                "ocrCandidates": ocr,
                "inpaintCandidates": {"inp-1": {"cleanReferenceRows": [{"pageId": "p1", "mae": 1.0, "psnr": 40.0}], "durationsMs": [15.0]}},
                "readingOrderRows": [{"language": "en", "reference": ["d1", "d2"], "prediction": ["d1", "d2"]}],
                "sfxRows": [{
                    "pageId": "p1", "blockId": "s1", "language": "en", "groundTruthKind": "sfx",
                    "groundTruthPixels": 20, "protectedFromEditing": True, "sentToTranslator": False,
                    "eraseInpaintOverlapPixels": 0, "changedPixelsAfterEncodeDecode": 0,
                    "destructiveEditPixels": 0, "protectedConflictSilentOverwrite": False,
                }],
                "pageSeconds": [1.0],
                "performanceScope": "local-ml-detector-ocr-role-inpaint-v1",
                "peakRamMiB": 512.0,
            },
            "startedAtUtc": "2026-08-19T12:00:00Z",
            "finishedAtUtc": "2026-08-19T12:01:00Z",
            "evidenceSha256": None,
        },
        # Deliberately bogus duplicate aggregates: schema-v2 report building must ignore them.
        "detection": {}, "detectionByLanguage": {}, "ocrRows": [], "readingOrderRows": [], "sfxRows": [],
        "qualityExtra": {}, "humanReview": {}, "translation": {}, "renderer": {}, "performance": {"pageSeconds": [999.0]},
        "runtime": {"pythonVersion": "bogus"},
    }
    seal_raw_execution(raw)
    return raw, plan


def test_schema2_report_recomputes_candidate_metrics_from_execution_trace():
    raw, _ = _schema2_raw()
    report = build_report(raw, _policy())
    det = next(item for item in report["candidates"] if item["candidateId"] == "det-1")
    en = next(item for item in report["candidates"] if item["candidateId"] == "en-1")
    assert det["metrics"]["dialogueRecall"] == 1.0
    assert det["metrics"]["precision"] == 1.0
    assert en["metrics"]["cer"] == 0.0
    assert report["performance"]["peakRamMiB"] == 512.0
    assert report["performance"]["scope"] == "local-ml-detector-ocr-role-inpaint-v1"
    assert report["runtime"]["pythonVersion"] == "test"


def test_schema2_manual_candidate_metric_override_cannot_change_report():
    raw, _ = _schema2_raw()
    raw["candidates"][0]["metrics"] = {"dialogueRecall": 0.0, "precision": 0.0, "f1": 0.0, "criticalFalseEraseCount": 999, "artworkFalsePositiveAreaRate": 1.0, "p95Ms": 9999, "peakMemoryMiB": 9999}
    raw["execution"]["machineEvidence"]["detectorCandidates"]["det-1"]["aggregate"] = {key: 0 for key in raw["execution"]["machineEvidence"]["detectorCandidates"]["det-1"]["aggregate"]}
    seal_raw_execution(raw)
    report = build_report(raw, _policy())
    det = next(item for item in report["candidates"] if item["candidateId"] == "det-1")
    assert det["metrics"]["dialogueRecall"] == 1.0
    assert det["metrics"]["criticalFalseEraseCount"] == 0


def test_execution_attestation_rejects_trace_tamper_and_run_plan_reuse(monkeypatch: pytest.MonkeyPatch):
    raw, plan = _schema2_raw()
    monkeypatch.setattr(execution, "dependency_lock_pins", lambda *args, **kwargs: plan["dependencyLocks"])
    validate_raw_execution(raw, run_plan=plan)
    raw["execution"]["machineEvidence"]["ocrCandidates"]["en-1"]["rows"][0]["prediction"] = "forged"
    with pytest.raises(BenchmarkExecutionError, match="evidence digest mismatch"):
        validate_raw_execution(raw, run_plan=plan)

    raw, plan = _schema2_raw()
    other = dict(plan)
    other["createdAtUtc"] = "2026-08-19T12:02:00Z"
    other["runPlanSha256"] = run_plan_digest(other)
    with pytest.raises(BenchmarkExecutionError, match="not produced for this run plan"):
        validate_raw_execution(raw, run_plan=other)


def test_deleting_sfx_trace_cannot_build_a_production_report():
    raw, _ = _schema2_raw()
    raw["execution"]["machineEvidence"]["sfxRows"] = []
    seal_raw_execution(raw)
    with pytest.raises(ValueError, match="must include ground-truth SFX evidence"):
        build_report(raw, _policy())


def test_execution_input_rehash_rejects_artifact_changed_after_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Small structural corpus is enough: execution input verification must rehash bytes
    # even before a production-size corpus is admitted by the release gate.
    image_path = tmp_path / "page.png"
    Image.new("RGB", (32, 32), "white").save(image_path)
    annotation_path = tmp_path / "annotation.json"
    annotation_path.write_text(json.dumps({"schemaVersion": 1, "blocks": [{"blockId": "d1", "kind": "dialogue", "text": "hello", "polygon": [[2, 2], [20, 2], [20, 10], [2, 10]], "readingOrder": 0}]}), encoding="utf-8")
    rights_review = {
        "schemaVersion": 1,
        "reviewRecordId": "rr1",
        "sourceId": "operator-owned-or-explicitly-permissioned",
        "sourceRevision": "test-v1",
        "reviewer": "tester",
        "reviewedAtUtc": "2026-08-19T12:00:00Z",
        "benchmarkUseAuthorized": True,
        "commercialV1QualificationAuthorized": True,
        "redistributionAuthorized": False,
        "coverageMode": "page-list",
        "pageIds": ["p1"],
        "evidence": [{"kind": "owned", "ref": "internal:rr1"}],
    }
    rights_dir = tmp_path / "rights"
    rights_dir.mkdir()
    rights_path = rights_dir / "rr1.json"
    rights_path.write_text(json.dumps(rights_review), encoding="utf-8")
    registry = load_source_registry()
    corpus = {
        "schemaVersion": 2, "policyRevision": "rev10-production-corpus-v2", "corpusId": "tiny-corpus",
        "sourceRegistryRevision": registry["registryRevision"], "sourceRegistrySha256": source_registry_digest(registry),
        "pages": [{
            "pageId": "p1", "language": "en", "imagePath": "page.png", "imageSha256": sha256_file(image_path),
            "annotationPath": "annotation.json", "annotationSha256": sha256_file(annotation_path), "features": [],
            "rights": {"reviewed": True, "benchmarkUseAuthorized": True, "basis": "owned", "source": "internal",
                       "redistributionAuthorized": False, "notes": "", "reviewRecordId": "rr1", "reviewedBy": "tester",
                       "reviewedAtUtc": "2026-08-19T12:00:00Z", "evidenceRef": "internal:rr1",
                       "sourceId": "operator-owned-or-explicitly-permissioned", "sourceRevision": "test-v1",
                       "reviewRecordPath": "rights/rr1.json", "reviewRecordSha256": sha256_file(rights_path)},
        }],
    }
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(json.dumps(corpus), encoding="utf-8")
    policy = {"schemaVersion": 1, "policyRevision": "tiny-policy", "candidateCoverage": {"ocr-en": ["family-a"]}}
    policy_path = tmp_path / "policy.json"; policy_path.write_text(json.dumps(policy), encoding="utf-8")
    artifacts = tmp_path / "artifacts"; artifacts.mkdir(); artifact = artifacts / "model.bin"; artifact.write_bytes(b"model-v1")
    catalog = {"schemaVersion": 1, "catalogRevision": "tiny-catalog", "artifacts": [{
        "artifactId": "model-a", "kind": "ocr", "upstreamProject": "owned", "upstreamRevision": "r1",
        "sourceUrl": "https://example.invalid/model", "expectedFilename": "model.bin", "sha256": sha256_path(artifact),
        "codeLicense": "Apache-2.0", "artifactLicenseStatus": "approved", "redistributionStatus": "local-only", "benchmarkUseStatus": "approved",
    }]}
    catalog_path = tmp_path / "catalog.json"; catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    candidate_plan = {"schemaVersion": 1, "planRevision": "tiny-plan", "candidates": [{"candidateId": "ocr-a", "component": "ocr-en", "family": "family-a", "artifactIds": ["model-a"]}], "supportArtifactIds": []}
    candidate_path = tmp_path / "candidate.json"; candidate_path.write_text(json.dumps(candidate_plan), encoding="utf-8")
    run_plan = {
        "schemaVersion": 2, "runPlanRevision": "rev11-production-benchmark-run-plan-v3", "createdAtUtc": "2026-08-19T12:00:00Z",
        "ready": True, "reasons": [], "corpusId": corpus["corpusId"], "corpusManifestSha256": sha256_bytes(canonical_json(corpus)),
        "policyRevision": policy["policyRevision"], "policySha256": sha256_bytes(canonical_json(policy)),
        "catalogRevision": catalog["catalogRevision"], "catalogSha256": sha256_bytes(canonical_json(catalog)),
        "candidatePlanRevision": candidate_plan["planRevision"], "candidatePlanSha256": candidate_plan_digest(candidate_plan),
        "executor": executor_pin(), "dependencyLocks": {"revision": "rev11-qualification-dependency-lock-pins-v1", "packageLockSha256": "sha256:" + "d" * 64, "uvLockSha256": "sha256:" + "c" * 64, "npmPackageCount": 2, "uvPackageCount": 2}, "artifactPins": [{"artifactId": "model-a", "sha256": catalog["artifacts"][0]["sha256"], "expectedFilename": "model.bin"}],
        "artifactReceiptSha256s": {"model-a": "sha256:" + "a" * 64},
    }
    run_plan["runPlanSha256"] = run_plan_digest(run_plan)
    review = {"schemaVersion": 1, "reviewRevision": "rev10-production-benchmark-review-v1", "reportId": "tiny-report", "runPlanSha256": run_plan["runPlanSha256"],
              "inpaintingCandidates": {}, "translation": {"adapterId": "a", "modelOrProviderRevision": "b", "contextMode": "c", "privacyMode": "d", "pagesReviewed": 0, "pagesByLanguage": {"en": 0, "ja": 0, "ko": 0, "zh-Hans": 0, "zh-Hant": 0}, "criticalFailures": 0, "arabicNaturalnessMean": 0.0},
              "renderer": {"adapterRevision": "r", "fontArtifactId": "f", "goldenSuiteRevision": "g", "arabicRendererGoldensRun": 0, "arabicRendererGoldensFailed": 0}}
    monkeypatch.setattr(execution, "verify_receipts", lambda *args, **kwargs: (True, [], []))
    monkeypatch.setattr(execution, "dependency_lock_pins", lambda *args, **kwargs: run_plan["dependencyLocks"])
    verify_execution_inputs(run_plan=run_plan, corpus_path=corpus_path, policy_path=policy_path, catalog_path=catalog_path, candidate_plan_path=candidate_path, artifacts_dir=artifacts, receipts_dir=tmp_path / "receipts", review=review)
    artifact.write_bytes(b"model-v2")
    with pytest.raises(BenchmarkExecutionError, match="artifact bytes changed"):
        verify_execution_inputs(run_plan=run_plan, corpus_path=corpus_path, policy_path=policy_path, catalog_path=catalog_path, candidate_plan_path=candidate_path, artifacts_dir=artifacts, receipts_dir=tmp_path / "receipts", review=review)



def test_detection_scoring_uses_local_pair_masks_and_preserves_sfx_critical_overlap():
    from mte_engine.pipeline.contracts import DetectedRegion

    blocks = [
        {"blockId": "d1", "kind": "dialogue", "polygon": [[10, 10], [50, 10], [50, 30], [10, 30]]},
        {"blockId": "s1", "kind": "sfx", "polygon": [[100, 10], [130, 10], [130, 30], [100, 30]]},
    ]
    predicted = [
        DetectedRegion("p1", ((10, 10), (50, 10), (50, 30), (10, 30)), 1.0, "horizontal"),
        DetectedRegion("p2", ((105, 12), (125, 12), (125, 28), (105, 28)), 1.0, "horizontal"),
    ]
    counts = execution._score_detection((1000, 100000), blocks, predicted)
    assert counts["truePositive"] == 1
    assert counts["falsePositive"] == 1
    assert counts["criticalFalseEraseCount"] == 1
    assert counts["groundTruthTextPixels"] > 0



def test_binary_mask_count_handles_direct_draw_and_imagechops_foreground_values():
    from PIL import ImageChops, ImageDraw

    mask = Image.new("1", (16, 16), 0)
    ImageDraw.Draw(mask).rectangle((2, 2, 5, 5), fill=1)
    assert execution._mask_pixel_count(mask) == 16
    logical = ImageChops.logical_and(mask, mask)
    assert execution._mask_pixel_count(logical) == 16
    assert execution._mask_overlap_pixels(mask, mask) == 16
