from __future__ import annotations

import importlib.metadata
import json
import math
import os
import platform
import statistics
import tempfile
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol, Sequence

from PIL import Image, ImageChops, ImageDraw

from ..config import EngineSettings
from ..pipeline.contracts import DetectedRegion, OcrResult
from ..pipeline.detector import ProductionDetector
from ..pipeline.inpaint import ProductionInpainter
from ..pipeline.ocr import ProductionOcrRouter
from ..pipeline.reading_order import HeuristicReadingOrder
from ..pipeline.roles import PRODUCTION_ROLE_REVISION, VisualEnclosureRoleClassifier
from ..production_runtime import materialize_model_directory
from .candidate_plan import candidate_plan_digest, load_candidate_plan
from .dependency_locks import dependency_lock_pins
from .catalog import artifact_by_id, load_catalog, resolve_artifact_path
from .common import canonical_json, is_sha256, require_dict, require_list, sha256_bytes, sha256_file, sha256_path
from .corpus import load_corpus
from .metrics import cer, psnr
from .provenance import verify_receipts
from .run_plan import load_run_plan
from .selection import select_winners

EXECUTOR_REVISION = "rev10-production-benchmark-executor-v1"
RAW_EXECUTION_SCHEMA_VERSION = 2
EXECUTION_ATTESTATION_REVISION = "rev10-benchmark-execution-attestation-v1"

# Every source file below can change benchmark semantics. A ready run-plan pins a
# digest over this exact set; editing any of them requires a new run-plan.
EXECUTOR_SOURCE_FILES = (
    "mte_engine/benchmark/execution.py",
    "mte_engine/benchmark/metrics.py",
    "mte_engine/benchmark/selection.py",
    "mte_engine/pipeline/contracts.py",
    "mte_engine/pipeline/detector.py",
    "mte_engine/pipeline/ocr.py",
    "mte_engine/pipeline/reading_order.py",
    "mte_engine/pipeline/roles.py",
    "mte_engine/pipeline/inpaint.py",
)

DETECTION_MATCH_IOU = 0.50


class BenchmarkExecutionError(ValueError):
    pass


class BenchmarkBackend(Protocol):
    def detector(self, *, candidate_id: str, model_path: Path) -> Any: ...
    def ocr(self, *, candidate_id: str, model_path: Path) -> Any: ...
    def inpainter(self, *, candidate_id: str, model_path: Path) -> Any: ...


class ProductionBenchmarkBackend:
    def detector(self, *, candidate_id: str, model_path: Path) -> ProductionDetector:
        return ProductionDetector(candidate_id=candidate_id, model_path=model_path)

    def ocr(self, *, candidate_id: str, model_path: Path) -> ProductionOcrRouter:
        component = _ocr_component(candidate_id)
        selected = {
            "ocrEnglish": candidate_id if component == "ocr-en" else "ppocrv6-small-en",
            "ocrJapanese": candidate_id if component == "ocr-ja" else "manga-ocr-ja",
            "ocrKorean": candidate_id if component == "ocr-ko" else "ppocrv5-ko",
            "ocrChinese": candidate_id if component == "ocr-zh" else "ppocrv6-small-zh",
        }
        # ProductionOcrRouter only dereferences the artifact belonging to the selected
        # source language, so supplying the tested artifact under its exact catalog ID
        # does not substitute another candidate.
        from ..pipeline.ocr import OCR_CANDIDATE_ARTIFACT

        artifact_id = OCR_CANDIDATE_ARTIFACT[candidate_id]
        return ProductionOcrRouter(selected=selected, artifact_paths={artifact_id: model_path})

    def inpainter(self, *, candidate_id: str, model_path: Path) -> ProductionInpainter:
        return ProductionInpainter(candidate_id=candidate_id, model_dir=model_path)


@dataclass(frozen=True, slots=True)
class _Page:
    page_id: str
    language: str
    image: Image.Image
    annotation: dict[str, Any]
    clean_reference: Image.Image | None


def executor_source_digest(engine_root: Path | None = None) -> str:
    root = (engine_root or Path(__file__).resolve().parents[2]).resolve()
    payload = bytearray()
    for relative in EXECUTOR_SOURCE_FILES:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise BenchmarkExecutionError(f"benchmark executor source is missing or unsafe: {relative}")
        name = relative.encode("utf-8")
        data = path.read_bytes()
        payload.extend(len(name).to_bytes(4, "big"))
        payload.extend(name)
        payload.extend(len(data).to_bytes(8, "big"))
        payload.extend(data)
    return sha256_bytes(bytes(payload))


def executor_pin(engine_root: Path | None = None) -> dict[str, str]:
    return {"revision": EXECUTOR_REVISION, "sourceSha256": executor_source_digest(engine_root)}


def raw_execution_digest(raw: dict[str, Any]) -> str:
    body = json.loads(json.dumps(raw, ensure_ascii=True))
    execution = require_dict(body.get("execution"), label="raw.execution")
    execution.pop("evidenceSha256", None)
    return sha256_bytes(canonical_json(body))


def seal_raw_execution(raw: dict[str, Any]) -> dict[str, Any]:
    execution = require_dict(raw.get("execution"), label="raw.execution")
    execution["evidenceSha256"] = raw_execution_digest(raw)
    return raw


def validate_raw_execution(raw: dict[str, Any], *, run_plan: dict[str, Any], engine_root: Path | None = None) -> None:
    if raw.get("schemaVersion") != RAW_EXECUTION_SCHEMA_VERSION:
        raise BenchmarkExecutionError("production raw benchmark must use schemaVersion 2 executor evidence")
    execution = require_dict(raw.get("execution"), label="raw.execution")
    if execution.get("attestationRevision") != EXECUTION_ATTESTATION_REVISION:
        raise BenchmarkExecutionError("raw benchmark execution attestation revision is unsupported")
    expected_executor = require_dict(run_plan.get("executor"), label="runPlan.executor")
    if execution.get("executorRevision") != expected_executor.get("revision"):
        raise BenchmarkExecutionError("raw benchmark executor revision does not match run plan")
    if execution.get("executorSourceSha256") != expected_executor.get("sourceSha256"):
        raise BenchmarkExecutionError("raw benchmark executor source digest does not match run plan")
    if expected_executor.get("revision") != EXECUTOR_REVISION or expected_executor.get("sourceSha256") != executor_source_digest(engine_root):
        raise BenchmarkExecutionError("current executor bytes do not match the executor pinned by the run plan")
    current_lock_pins = dependency_lock_pins((engine_root or Path(__file__).resolve().parents[2]).resolve().parent)
    if run_plan.get("dependencyLocks") != current_lock_pins:
        raise BenchmarkExecutionError("current dependency lock bytes do not match the locks pinned by the run plan")
    if raw.get("runPlanSha256") != run_plan.get("runPlanSha256") or execution.get("runPlanSha256") != run_plan.get("runPlanSha256"):
        raise BenchmarkExecutionError("raw benchmark was not produced for this run plan")
    if raw.get("candidatePlanSha256") != run_plan.get("candidatePlanSha256"):
        raise BenchmarkExecutionError("raw benchmark candidate plan does not match run plan")
    if raw.get("corpusManifestSha256") != run_plan.get("corpusManifestSha256"):
        raise BenchmarkExecutionError("raw benchmark corpus does not match run plan")
    pins = require_dict(execution.get("artifactSha256s"), label="raw.execution.artifactSha256s")
    expected_pins = {item["artifactId"]: item["sha256"] for item in require_list(run_plan.get("artifactPins"), label="runPlan.artifactPins")}
    if pins != expected_pins:
        raise BenchmarkExecutionError("raw benchmark artifact pins do not exactly match run plan")
    review_sha = execution.get("reviewRecordSha256")
    if not is_sha256(review_sha):
        raise BenchmarkExecutionError("raw benchmark review record digest is missing")
    review = require_dict(execution.get("reviewSnapshot"), label="raw.execution.reviewSnapshot")
    if review.get("reviewRecordSha256") != review_sha:
        raise BenchmarkExecutionError("raw benchmark review snapshot does not match the recorded review digest")
    review_body = dict(review)
    review_body.pop("reviewRecordSha256", None)
    if sha256_bytes(canonical_json(review_body)) != review_sha:
        raise BenchmarkExecutionError("raw benchmark embedded review snapshot digest mismatch")
    evidence = require_dict(execution.get("machineEvidence"), label="raw.execution.machineEvidence")
    detector_ids = {item["candidateId"] for item in require_list(raw.get("candidates"), label="raw.candidates") if item.get("component") == "detector"}
    ocr_ids = {item["candidateId"] for item in raw["candidates"] if isinstance(item, dict) and str(item.get("component", "")).startswith("ocr-")}
    inpaint_ids = {item["candidateId"] for item in raw["candidates"] if isinstance(item, dict) and item.get("component") == "inpaint"}
    if set(require_dict(evidence.get("detectorCandidates"), label="machineEvidence.detectorCandidates")) != detector_ids:
        raise BenchmarkExecutionError("detector machine evidence does not exactly cover benchmark candidates")
    if set(require_dict(evidence.get("ocrCandidates"), label="machineEvidence.ocrCandidates")) != ocr_ids:
        raise BenchmarkExecutionError("OCR machine evidence does not exactly cover benchmark candidates")
    if set(require_dict(evidence.get("inpaintCandidates"), label="machineEvidence.inpaintCandidates")) != inpaint_ids:
        raise BenchmarkExecutionError("inpainting machine evidence does not exactly cover benchmark candidates")
    if execution.get("evidenceSha256") != raw_execution_digest(raw):
        raise BenchmarkExecutionError("raw benchmark execution evidence digest mismatch")


def verify_execution_inputs(
    *,
    run_plan: dict[str, Any],
    corpus_path: Path,
    policy_path: Path,
    catalog_path: Path,
    candidate_plan_path: Path,
    artifacts_dir: Path,
    receipts_dir: Path,
    review: dict[str, Any],
    engine_root: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    expected_executor = require_dict(run_plan.get("executor"), label="runPlan.executor")
    current_pin = executor_pin(engine_root)
    if expected_executor != current_pin:
        raise BenchmarkExecutionError("current benchmark executor does not match the run-plan pin")
    current_lock_pins = dependency_lock_pins((engine_root or Path(__file__).resolve().parents[2]).resolve().parent)
    if run_plan.get("dependencyLocks") != current_lock_pins:
        raise BenchmarkExecutionError("current dependency lock bytes do not match the locks pinned by the run plan")

    from .gate import load_policy

    corpus = load_corpus(corpus_path, verify_files=True)
    policy = load_policy(policy_path)
    catalog = load_catalog(catalog_path)
    candidate_plan = load_candidate_plan(candidate_plan_path, catalog=catalog, policy=policy)
    if sha256_bytes(canonical_json(corpus)) != run_plan["corpusManifestSha256"]:
        raise BenchmarkExecutionError("corpus manifest changed after run-plan creation")
    if sha256_bytes(canonical_json(policy)) != run_plan["policySha256"]:
        raise BenchmarkExecutionError("benchmark policy changed after run-plan creation")
    if sha256_bytes(canonical_json(catalog)) != run_plan["catalogSha256"]:
        raise BenchmarkExecutionError("model catalog changed after run-plan creation")
    if candidate_plan_digest(candidate_plan) != run_plan["candidatePlanSha256"]:
        raise BenchmarkExecutionError("candidate plan changed after run-plan creation")

    expected_pins = {item["artifactId"]: item for item in require_list(run_plan["artifactPins"], label="runPlan.artifactPins")}
    by_id = artifact_by_id(catalog)
    for artifact_id, pin in expected_pins.items():
        item = by_id.get(artifact_id)
        if item is None:
            raise BenchmarkExecutionError(f"run-plan artifact disappeared from catalog: {artifact_id}")
        path = resolve_artifact_path(artifacts_dir, pin["expectedFilename"], artifact_id=artifact_id)
        if not path.exists() or sha256_path(path) != pin["sha256"]:
            raise BenchmarkExecutionError(f"artifact bytes changed after run-plan creation: {artifact_id}")
    receipt_ok, receipt_reasons, _ = verify_receipts(catalog, list(expected_pins), receipts_dir=receipts_dir, artifacts_dir=artifacts_dir)
    if not receipt_ok:
        raise BenchmarkExecutionError("artifact receipt verification failed: " + "; ".join(receipt_reasons))
    _validate_review(review, run_plan=run_plan, candidate_plan=candidate_plan)
    return corpus, policy, catalog, candidate_plan


def execute_benchmark(
    *,
    run_plan_path: Path,
    corpus_path: Path,
    policy_path: Path,
    catalog_path: Path,
    candidate_plan_path: Path,
    artifacts_dir: Path,
    receipts_dir: Path,
    review_path: Path,
    output_path: Path,
    backend: BenchmarkBackend | None = None,
    engine_root: Path | None = None,
) -> dict[str, Any]:
    run_plan = load_run_plan(run_plan_path, require_ready=True)
    review = _load_review(review_path)
    corpus, policy, catalog, candidate_plan = verify_execution_inputs(
        run_plan=run_plan,
        corpus_path=corpus_path,
        policy_path=policy_path,
        catalog_path=catalog_path,
        candidate_plan_path=candidate_plan_path,
        artifacts_dir=artifacts_dir,
        receipts_dir=receipts_dir,
        review=review,
        engine_root=engine_root,
    )
    backend = backend or ProductionBenchmarkBackend()
    started = _utc_now()
    with tempfile.TemporaryDirectory(prefix="mte-benchmark-runtime-") as temp_dir:
        materialized = _materialize_artifacts(run_plan, catalog, artifacts_dir, Path(temp_dir))
        pages = _load_pages(corpus_path, corpus)
        candidates, detector_evidence, ocr_evidence, inpaint_evidence = _run_candidates(
            pages=pages,
            candidate_plan=candidate_plan,
            materialized=materialized,
            review=review,
            backend=backend,
        )
        selected = select_winners(candidates, policy)
        raw = _assemble_raw(
            pages=pages,
            corpus=corpus,
            policy=policy,
            candidate_plan=candidate_plan,
            run_plan=run_plan,
            review=review,
            candidates=candidates,
            selected=selected,
            detector_evidence=detector_evidence,
            ocr_evidence=ocr_evidence,
            inpaint_evidence=inpaint_evidence,
            materialized=materialized,
            backend=backend,
            started=started,
        )
    seal_raw_execution(raw)
    # Validate the bytes we are about to persist against the same run-plan pin.
    validate_raw_execution(raw, run_plan=run_plan, engine_root=engine_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(output_path.suffix + ".tmp")
    tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(output_path)
    return raw


def _run_candidates(*, pages: Sequence[_Page], candidate_plan: dict[str, Any], materialized: dict[str, Path], review: dict[str, Any], backend: BenchmarkBackend):
    candidates: list[dict[str, Any]] = []
    detector_evidence: dict[str, Any] = {}
    ocr_evidence: dict[str, Any] = {}
    inpaint_evidence: dict[str, Any] = {}
    for raw_candidate in candidate_plan["candidates"]:
        candidate = dict(raw_candidate)
        candidate_id = str(candidate["candidateId"])
        component = str(candidate["component"])
        artifact_id = str(candidate["artifactIds"][0])
        model_path = materialized[artifact_id]
        if component == "detector":
            metrics, evidence = _benchmark_detector(candidate_id, model_path, pages, backend)
            detector_evidence[candidate_id] = evidence
        elif component.startswith("ocr-"):
            metrics, evidence = _benchmark_ocr(candidate_id, component, model_path, pages, backend)
            ocr_evidence[candidate_id] = evidence
        elif component == "inpaint":
            metrics, evidence = _benchmark_inpaint(candidate_id, model_path, pages, review, backend)
            inpaint_evidence[candidate_id] = evidence
        else:
            raise BenchmarkExecutionError(f"unsupported benchmark component: {component}")
        candidate["metrics"] = metrics
        candidates.append(candidate)
    return candidates, detector_evidence, ocr_evidence, inpaint_evidence


def _benchmark_detector(candidate_id: str, model_path: Path, pages: Sequence[_Page], backend: BenchmarkBackend):
    detector = backend.detector(candidate_id=candidate_id, model_path=model_path)
    totals = _empty_detection_counts()
    by_language: dict[str, dict[str, int]] = {}
    durations: list[float] = []
    page_rows: list[dict[str, Any]] = []
    for page in pages:
        start = time.perf_counter()
        predicted = tuple(detector.detect(page.image, source_language=page.language, layout_mode="auto"))
        durations.append((time.perf_counter() - start) * 1000.0)
        counts = _score_detection(page.image.size, page.annotation["blocks"], predicted)
        _merge_counts(totals, counts)
        lang_counts = by_language.setdefault(page.language, _empty_detection_counts())
        _merge_counts(lang_counts, counts)
        page_rows.append({"pageId": page.page_id, "language": page.language, "counts": counts, "predictedRegions": len(predicted)})
    metrics = _candidate_detector_metrics(totals, durations)
    return metrics, {"aggregate": totals, "byLanguage": by_language, "pageRows": page_rows, "durationsMs": durations}


def _benchmark_ocr(candidate_id: str, component: str, model_path: Path, pages: Sequence[_Page], backend: BenchmarkBackend):
    language_set = _component_languages(component)
    router = backend.ocr(candidate_id=candidate_id, model_path=model_path)
    rows: list[dict[str, Any]] = []
    durations: list[float] = []
    for page in pages:
        if page.language not in language_set:
            continue
        for block in page.annotation["blocks"]:
            if block.get("kind") not in {"dialogue", "narration"}:
                continue
            region = _region_from_block(block)
            start = time.perf_counter()
            result = router.recognize(page.image, region, source_language=page.language)
            durations.append((time.perf_counter() - start) * 1000.0)
            rows.append({
                "pageId": page.page_id,
                "blockId": block["blockId"],
                "language": page.language,
                "reference": block["text"],
                "prediction": result.text,
                "confidence": float(result.confidence),
            })
    if not rows:
        raise BenchmarkExecutionError(f"OCR candidate has no eligible corpus rows: {candidate_id}")
    metrics = {
        "cer": statistics.fmean(cer(str(row["reference"]), str(row["prediction"])) for row in rows),
        "p95Ms": _p95(durations),
        "modelBytes": _path_bytes(model_path),
    }
    return metrics, {"rows": rows, "durationsMs": durations, "modelBytes": _path_bytes(model_path)}


def _benchmark_inpaint(candidate_id: str, model_path: Path, pages: Sequence[_Page], review: dict[str, Any], backend: BenchmarkBackend):
    inpainter = backend.inpainter(candidate_id=candidate_id, model_path=model_path)
    rows: list[dict[str, Any]] = []
    durations: list[float] = []
    for page in pages:
        if page.clean_reference is None:
            continue
        mask = _mask_for_blocks(page.image.size, [b for b in page.annotation["blocks"] if b.get("kind") in {"dialogue", "narration"}])
        start = time.perf_counter()
        result = inpainter.inpaint(page.image, mask)
        durations.append((time.perf_counter() - start) * 1000.0)
        mae, psnr_value = _masked_image_quality(result, page.clean_reference, mask)
        rows.append({"pageId": page.page_id, "mae": mae, "psnr": psnr_value})
    review_entry = require_dict(require_dict(review["inpaintingCandidates"], label="review.inpaintingCandidates").get(candidate_id), label=f"review.inpaintingCandidates.{candidate_id}")
    metrics = {
        "humanCriticalFailures": int(review_entry["criticalFailures"]),
        "humanScore": float(review_entry["humanScore"]),
        "p95Ms": _p95(durations),
        "peakMemoryMiB": 0.0,
    }
    return metrics, {"cleanReferenceRows": rows, "durationsMs": durations}


def _assemble_raw(*, pages: Sequence[_Page], corpus: dict[str, Any], policy: dict[str, Any], candidate_plan: dict[str, Any], run_plan: dict[str, Any], review: dict[str, Any], candidates: list[dict[str, Any]], selected: dict[str, str], detector_evidence: dict[str, Any], ocr_evidence: dict[str, Any], inpaint_evidence: dict[str, Any], materialized: dict[str, Path], backend: BenchmarkBackend, started: str) -> dict[str, Any]:
    selected_detector = detector_evidence[selected["detector"]]
    detection = selected_detector["aggregate"]
    detection_by_language = selected_detector["byLanguage"]
    ocr_rows: list[dict[str, Any]] = []
    for key in ("ocrEnglish", "ocrJapanese", "ocrKorean", "ocrChinese"):
        for row in ocr_evidence[selected[key]]["rows"]:
            ocr_rows.append({"language": row["language"], "reference": row["reference"], "prediction": row["prediction"]})
    reading_rows = _reading_order_rows(pages)
    sfx_rows, page_seconds = _sfx_and_performance_rows(pages, selected, materialized, backend)
    selected_inpaint = inpaint_evidence[selected["inpainter"]]["cleanReferenceRows"]
    review_translation = require_dict(review["translation"], label="review.translation")
    review_renderer = require_dict(review["renderer"], label="review.renderer")
    human_review = {
        "translationPagesReviewed": int(review_translation["pagesReviewed"]),
        "translationPagesByLanguage": dict(review_translation["pagesByLanguage"]),
        "inpaintingPagesReviewed": int(review["inpaintingCandidates"][selected["inpainter"]]["pagesReviewed"]),
        "criticalTranslationFailures": int(review_translation["criticalFailures"]),
        "criticalInpaintingFailures": int(review["inpaintingCandidates"][selected["inpainter"]]["criticalFailures"]),
        "arabicNaturalnessMean": float(review_translation["arabicNaturalnessMean"]),
    }
    inpaint_mae = statistics.fmean(row["mae"] for row in selected_inpaint) if selected_inpaint else None
    finite_psnr = [row["psnr"] for row in selected_inpaint if math.isfinite(row["psnr"])]
    inpaint_psnr = statistics.fmean(finite_psnr) if finite_psnr else None
    return {
        "schemaVersion": RAW_EXECUTION_SCHEMA_VERSION,
        "reportId": str(review["reportId"]),
        "corpusId": corpus["corpusId"],
        "corpusManifestSha256": run_plan["corpusManifestSha256"],
        "candidatePlanSha256": run_plan["candidatePlanSha256"],
        "runPlanSha256": run_plan["runPlanSha256"],
        "execution": {
            "attestationRevision": EXECUTION_ATTESTATION_REVISION,
            "executorRevision": run_plan["executor"]["revision"],
            "executorSourceSha256": run_plan["executor"]["sourceSha256"],
            "runPlanSha256": run_plan["runPlanSha256"],
            "artifactSha256s": {item["artifactId"]: item["sha256"] for item in run_plan["artifactPins"]},
            "reviewRecordSha256": review["reviewRecordSha256"],
            "reviewSnapshot": review,
            "runtime": _runtime_record(),
            "machineEvidence": {
                "detectorCandidates": detector_evidence,
                "ocrCandidates": ocr_evidence,
                "inpaintCandidates": inpaint_evidence,
                "readingOrderRows": reading_rows,
                "sfxRows": sfx_rows,
                "pageSeconds": page_seconds,
                "performanceScope": "local-ml-detector-ocr-role-inpaint-v1",
                "peakRamMiB": _process_peak_rss_mib(),
            },
            "startedAtUtc": started,
            "finishedAtUtc": _utc_now(),
            "evidenceSha256": None,
        },
        "runtime": _runtime_record(),
        "candidates": candidates,
        "detection": detection,
        "detectionByLanguage": detection_by_language,
        "ocrRows": ocr_rows,
        "readingOrderRows": reading_rows,
        "sfxRows": sfx_rows,
        "qualityExtra": {
            "arabicRendererGoldensRun": int(review_renderer["arabicRendererGoldensRun"]),
            "arabicRendererGoldensFailed": int(review_renderer["arabicRendererGoldensFailed"]),
            "inpainting": {"cleanReferencePages": len(selected_inpaint), "mae": inpaint_mae, "psnrMean": inpaint_psnr},
        },
        "humanReview": human_review,
        "translation": {
            "adapterId": review_translation["adapterId"],
            "modelOrProviderRevision": review_translation["modelOrProviderRevision"],
            "contextMode": review_translation["contextMode"],
            "privacyMode": review_translation["privacyMode"],
            "roleClassifierRevision": PRODUCTION_ROLE_REVISION,
        },
        "renderer": {
            "adapterRevision": review_renderer["adapterRevision"],
            "fontArtifactId": review_renderer["fontArtifactId"],
            "goldenSuiteRevision": review_renderer["goldenSuiteRevision"],
        },
        "performance": {
            "scope": "local-ml-detector-ocr-role-inpaint-v1",
            "pageSeconds": page_seconds,
            "peakRamMiB": _process_peak_rss_mib(),
            "peakVramMiB": 0.0,
            "modelLoadSeconds": 0.0,
            "stageMs": {},
            "resultBytes": {},
        },
    }


def _sfx_and_performance_rows(pages: Sequence[_Page], selected: dict[str, str], materialized: dict[str, Path], backend: BenchmarkBackend):
    """Audit protected GT blocks and measure the selected local ML pipeline.

    SFX safety uses ground-truth protected regions so a detector miss cannot hide a
    destructive edit. Performance is measured separately on detector-produced
    regions and therefore reflects the actual local detector->OCR->role->inpaint
    path rather than ground-truth crops. Translation/network and Arabic rendering
    are intentionally outside this local-ML timing scope and have separate gates.
    """
    from ..pipeline.detector import PADDLE_DETECTOR_CANDIDATES
    from ..pipeline.ocr import OCR_CANDIDATE_ARTIFACT

    ocr_models: dict[str, Any] = {}
    for key in ("ocrEnglish", "ocrJapanese", "ocrKorean", "ocrChinese"):
        candidate = selected[key]
        artifact_id = OCR_CANDIDATE_ARTIFACT[candidate]
        ocr_models[key] = backend.ocr(candidate_id=candidate, model_path=materialized[artifact_id])
    detector_id = selected["detector"]
    detector_artifact = PADDLE_DETECTOR_CANDIDATES[detector_id]
    detector = backend.detector(candidate_id=detector_id, model_path=materialized[detector_artifact])
    inpainter_id = selected["inpainter"]
    inpaint_artifact = "lama-big" if inpainter_id == "lama-inpaint" else "aot-gan-places2"
    inpainter = backend.inpainter(candidate_id=inpainter_id, model_path=materialized[inpaint_artifact])
    role = VisualEnclosureRoleClassifier()
    rows: list[dict[str, Any]] = []
    page_seconds: list[float] = []

    for page in pages:
        router = ocr_models[_selected_ocr_key(page.language)]

        # Performance path: use detector output, never corpus annotations.
        page_start = time.perf_counter()
        detected = tuple(detector.detect(page.image, source_language=page.language, layout_mode="auto"))
        editable_regions: list[DetectedRegion] = []
        for region in detected:
            result = router.recognize(page.image, region, source_language=page.language)
            decision = role.classify(page.image, region, result)
            if decision.processing_action == "translate-replace":
                editable_regions.append(region)
        performance_mask = _mask_for_regions(page.image.size, editable_regions)
        if performance_mask.getbbox() is not None:
            inpainter.inpaint(page.image, performance_mask)
        page_seconds.append(time.perf_counter() - page_start)

        # Safety path: independently audit every GT SFX/uncertain region. This may
        # repeat OCR/inpaint work, but it prevents detector misses from removing the
        # protected-region evidence required by the release gate.
        erase_blocks: list[dict[str, Any]] = []
        block_results: dict[str, tuple[dict[str, Any], Any]] = {}
        for block in page.annotation["blocks"]:
            region = _region_from_block(block, include_kind_hint=False)
            result = router.recognize(page.image, region, source_language=page.language)
            decision = role.classify(page.image, region, result)
            block_results[str(block["blockId"])] = (block, decision)
            if decision.processing_action == "translate-replace":
                erase_blocks.append(block)
        erase_mask = _mask_for_blocks(page.image.size, erase_blocks)
        if erase_mask.getbbox() is not None:
            edited = inpainter.inpaint(page.image, erase_mask)
        else:
            edited = page.image.convert("RGBA")
        buf = BytesIO()
        edited.save(buf, format="PNG")
        buf.seek(0)
        decoded = Image.open(buf).convert("RGBA")
        source_rgba = page.image.convert("RGBA")
        for block, decision in block_results.values():
            if block.get("kind") not in {"sfx", "uncertain"}:
                continue
            block_mask = _mask_for_blocks(page.image.size, [block])
            gt_pixels = _mask_pixel_count(block_mask)
            erase_overlap = _mask_overlap_pixels(block_mask, erase_mask)
            changed = _changed_pixels(source_rgba, decoded, block_mask)
            rows.append({
                "pageId": page.page_id,
                "blockId": block["blockId"],
                "language": page.language,
                "groundTruthKind": block["kind"],
                "groundTruthPixels": gt_pixels,
                "protectedFromEditing": bool(decision.protected_from_editing),
                "sentToTranslator": decision.processing_action == "translate-replace",
                "eraseInpaintOverlapPixels": erase_overlap,
                "changedPixelsAfterEncodeDecode": changed,
                "destructiveEditPixels": changed,
                "protectedConflictSilentOverwrite": False,
            })
    return rows, page_seconds

def _load_pages(corpus_path: Path, corpus: dict[str, Any]) -> list[_Page]:
    result: list[_Page] = []
    for page in corpus["pages"]:
        image_path = corpus_path.parent / page["imagePath"]
        annotation_path = corpus_path.parent / page["annotationPath"]
        image = Image.open(image_path).convert("RGBA")
        annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
        clean = None
        if isinstance(page.get("cleanReferencePath"), str):
            clean = Image.open(corpus_path.parent / page["cleanReferencePath"]).convert("RGBA")
        result.append(_Page(str(page["pageId"]), str(page["language"]), image, annotation, clean))
    return result


def _materialize_artifacts(run_plan: dict[str, Any], catalog: dict[str, Any], artifacts_dir: Path, temp_dir: Path) -> dict[str, Path]:
    settings = EngineSettings(data_dir=temp_dir)
    by_id = artifact_by_id(catalog)
    result: dict[str, Path] = {}
    for pin in run_plan["artifactPins"]:
        artifact_id = pin["artifactId"]
        source = resolve_artifact_path(artifacts_dir, pin["expectedFilename"], artifact_id=artifact_id)
        item = by_id[artifact_id]
        if item.get("kind") == "font":
            result[artifact_id] = source
        else:
            result[artifact_id] = materialize_model_directory(settings, artifact_id=artifact_id, source=source, expected_sha256=pin["sha256"])
    return result


def _score_detection(image_size: tuple[int, int], blocks: list[dict[str, Any]], predicted: Sequence[DetectedRegion]) -> dict[str, int]:
    targets = [b for b in blocks if b.get("kind") in {"dialogue", "narration"}]
    protected = [b for b in blocks if b.get("kind") in {"sfx", "uncertain", "other"}]
    pairs: list[tuple[float, int, int]] = []
    for pi, region in enumerate(predicted):
        for gi, block in enumerate(targets):
            iou = _polygon_iou(image_size, region.polygon, _block_polygon(block))
            if iou >= DETECTION_MATCH_IOU:
                pairs.append((iou, pi, gi))
    matched_p: set[int] = set()
    matched_g: set[int] = set()
    for _, pi, gi in sorted(pairs, reverse=True):
        if pi not in matched_p and gi not in matched_g:
            matched_p.add(pi)
            matched_g.add(gi)

    # Keep only a small number of page-sized one-bit masks. Creating one full-size
    # mask per predicted region is unsafe for long webtoons and can turn a valid
    # benchmark into a multi-gigabyte allocation.
    pred_union = _mask_for_regions(image_size, predicted)
    target_union = _mask_for_blocks(image_size, targets)
    all_text_union = _mask_for_blocks(image_size, blocks)
    artwork_area = image_size[0] * image_size[1] - _mask_pixel_count(all_text_union)
    artwork_fp = _mask_outside_pixels(pred_union, all_text_union)
    overreach = _mask_outside_pixels(pred_union, target_union)
    undercoverage = _mask_outside_pixels(target_union, pred_union)
    critical = 0
    protected_polygons = [_block_polygon(block) for block in protected]
    for region in predicted:
        if any(_polygon_overlap_pixels(image_size, region.polygon, polygon) > 0 for polygon in protected_polygons):
            critical += 1
    return {
        "truePositive": len(matched_g),
        "falsePositive": len(predicted) - len(matched_p),
        "falseNegative": len(targets) - len(matched_g),
        "falseEraseCandidateCount": critical,
        "criticalFalseEraseCount": critical,
        "artworkFalsePositiveArea": artwork_fp,
        "artworkArea": max(0, artwork_area),
        "maskOverreachPixels": overreach,
        "maskUndercoveragePixels": undercoverage,
        "groundTruthTextPixels": _mask_pixel_count(target_union),
    }

def _candidate_detector_metrics(counts: dict[str, int], durations: list[float]) -> dict[str, Any]:
    tp = counts["truePositive"]
    fp = counts["falsePositive"]
    fn = counts["falseNegative"]
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    f1 = 2 * precision * recall / max(1e-12, precision + recall)
    return {
        "dialogueRecall": recall,
        "precision": precision,
        "f1": f1,
        "criticalFalseEraseCount": counts["criticalFalseEraseCount"],
        "artworkFalsePositiveAreaRate": counts["artworkFalsePositiveArea"] / max(1, counts["artworkArea"]),
        "p95Ms": _p95(durations),
        "peakMemoryMiB": 0.0,
    }


def _reading_order_rows(pages: Sequence[_Page]) -> list[dict[str, Any]]:
    orderer = HeuristicReadingOrder()
    rows: list[dict[str, Any]] = []
    for page in pages:
        blocks = [b for b in page.annotation["blocks"] if b.get("kind") in {"dialogue", "narration"}]
        if len(blocks) < 2 or any(not isinstance(b.get("readingOrder"), int) for b in blocks):
            continue
        reference = [str(b["blockId"]) for b in sorted(blocks, key=lambda b: (int(b["readingOrder"]), str(b["blockId"])))]
        regions = [_region_from_block(b) for b in blocks]
        predicted = [r.region_id for r in orderer.order(regions, image_size=page.image.size, source_language=page.language, layout_mode="auto")]
        rows.append({"pageId": page.page_id, "language": page.language, "reference": reference, "prediction": predicted})
    return rows


def _region_from_block(block: dict[str, Any], *, include_kind_hint: bool = False) -> DetectedRegion:
    polygon = tuple((int(p[0]), int(p[1])) for p in block["polygon"])
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    orientation = "horizontal" if max(xs) - min(xs) >= max(ys) - min(ys) else "vertical"
    return DetectedRegion(
        region_id=str(block["blockId"]),
        polygon=polygon,
        confidence=1.0,
        orientation_hint=orientation,
        text_hint=None,
        kind_hint=str(block["kind"]) if include_kind_hint else None,
    )


def _mask_for_region(size: tuple[int, int], region: DetectedRegion) -> Image.Image:
    mask = Image.new("1", size, 0)
    ImageDraw.Draw(mask).polygon(list(region.polygon), fill=1)
    return mask


def _mask_for_blocks(size: tuple[int, int], blocks: Sequence[dict[str, Any]]) -> Image.Image:
    mask = Image.new("1", size, 0)
    draw = ImageDraw.Draw(mask)
    for block in blocks:
        draw.polygon([(int(p[0]), int(p[1])) for p in block["polygon"]], fill=1)
    return mask


def _mask_for_regions(size: tuple[int, int], regions: Sequence[DetectedRegion]) -> Image.Image:
    mask = Image.new("1", size, 0)
    draw = ImageDraw.Draw(mask)
    for region in regions:
        draw.polygon([(int(x), int(y)) for x, y in region.polygon], fill=1)
    return mask


def _block_polygon(block: dict[str, Any]) -> tuple[tuple[int, int], ...]:
    return tuple((int(p[0]), int(p[1])) for p in block["polygon"])


def _polygon_overlap_pixels(size: tuple[int, int], a: Sequence[tuple[int, int]], b: Sequence[tuple[int, int]]) -> int:
    bounds = _local_union_bounds(size, a, b)
    if bounds is None:
        return 0
    x0, y0, x1, y1 = bounds
    local_size = (x1 - x0 + 1, y1 - y0 + 1)
    ma = Image.new("1", local_size, 0)
    mb = Image.new("1", local_size, 0)
    ImageDraw.Draw(ma).polygon([(int(x) - x0, int(y) - y0) for x, y in a], fill=1)
    ImageDraw.Draw(mb).polygon([(int(x) - x0, int(y) - y0) for x, y in b], fill=1)
    return _mask_overlap_pixels(ma, mb)


def _polygon_iou(size: tuple[int, int], a: Sequence[tuple[int, int]], b: Sequence[tuple[int, int]]) -> float:
    bounds = _local_union_bounds(size, a, b)
    if bounds is None:
        return 0.0
    x0, y0, x1, y1 = bounds
    local_size = (x1 - x0 + 1, y1 - y0 + 1)
    ma = Image.new("1", local_size, 0)
    mb = Image.new("1", local_size, 0)
    ImageDraw.Draw(ma).polygon([(int(x) - x0, int(y) - y0) for x, y in a], fill=1)
    ImageDraw.Draw(mb).polygon([(int(x) - x0, int(y) - y0) for x, y in b], fill=1)
    intersection = _mask_overlap_pixels(ma, mb)
    union = _mask_pixel_count(ImageChops.logical_or(ma, mb))
    return intersection / max(1, union)


def _local_union_bounds(size: tuple[int, int], a: Sequence[tuple[int, int]], b: Sequence[tuple[int, int]]) -> tuple[int, int, int, int] | None:
    if not a or not b:
        return None
    width, height = size
    ax0, ay0, ax1, ay1 = _polygon_bounds(a)
    bx0, by0, bx1, by1 = _polygon_bounds(b)
    # Fast reject before allocating any local mask.
    if ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0:
        return None
    x0 = max(0, min(ax0, bx0))
    y0 = max(0, min(ay0, by0))
    x1 = min(width - 1, max(ax1, bx1))
    y1 = min(height - 1, max(ay1, by1))
    if x1 < x0 or y1 < y0:
        return None
    return x0, y0, x1, y1


def _polygon_bounds(points: Sequence[tuple[int, int]]) -> tuple[int, int, int, int]:
    xs = [int(x) for x, _ in points]
    ys = [int(y) for _, y in points]
    return min(xs), min(ys), max(xs), max(ys)


def _mask_union(size: tuple[int, int], masks: Sequence[Image.Image]) -> Image.Image:
    result = Image.new("1", size, 0)
    for mask in masks:
        result = ImageChops.logical_or(result, mask.convert("1"))
    return result


def _mask_pixel_count(mask: Image.Image) -> int:
    # Mode 1 keeps long webtoon masks compact (one bit/pixel). Pillow may expose
    # directly drawn foreground pixels as histogram bin 1 while ImageChops logical
    # operations expose them as bin 255, so count every non-zero bin.
    histogram = mask.convert("1").histogram()
    return int(sum(histogram[1:]))


def _mask_overlap_pixels(a: Image.Image, b: Image.Image) -> int:
    return _mask_pixel_count(ImageChops.logical_and(a.convert("1"), b.convert("1")))


def _mask_outside_pixels(a: Image.Image, b: Image.Image) -> int:
    return _mask_pixel_count(ImageChops.logical_and(a.convert("1"), ImageChops.invert(b.convert("1"))))


def _mask_iou(a: Image.Image, b: Image.Image) -> float:
    intersection = _mask_overlap_pixels(a, b)
    union = _mask_pixel_count(ImageChops.logical_or(a.convert("1"), b.convert("1")))
    return intersection / max(1, union)


def _changed_pixels(source: Image.Image, result: Image.Image, mask: Image.Image) -> int:
    diff = ImageChops.difference(source.convert("RGBA"), result.convert("RGBA")).convert("RGB")
    changed = diff.convert("L").point(lambda v: 255 if v else 0).convert("1")
    return _mask_overlap_pixels(changed, mask)


def _masked_image_quality(result: Image.Image, reference: Image.Image, mask: Image.Image) -> tuple[float, float]:
    try:
        import numpy as np
    except ImportError as exc:
        raise BenchmarkExecutionError("production benchmark quality metrics require numpy") from exc
    m = np.asarray(mask.convert("L"), dtype=np.uint8) > 0
    if not bool(m.any()):
        return 0.0, math.inf
    a = np.asarray(result.convert("RGB"), dtype=np.float32)[m]
    b = np.asarray(reference.convert("RGB"), dtype=np.float32)[m]
    delta = a - b
    mae = float(np.mean(np.abs(delta)))
    mse = float(np.mean(delta * delta))
    # JSON forbids Infinity. Exact matches use a fixed serialization ceiling; MAE=0
    # still preserves the fact that the measured candidate was pixel-perfect.
    return mae, 100.0 if mse <= 0.0 else psnr(mse=mse)


def _empty_detection_counts() -> dict[str, int]:
    return {key: 0 for key in (
        "truePositive", "falsePositive", "falseNegative", "falseEraseCandidateCount", "criticalFalseEraseCount",
        "artworkFalsePositiveArea", "artworkArea", "maskOverreachPixels", "maskUndercoveragePixels", "groundTruthTextPixels",
    )}


def _merge_counts(target: dict[str, int], source: dict[str, int]) -> None:
    for key in target:
        target[key] += int(source[key])


def _p95(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    index = min(len(ordered) - 1, max(0, math.ceil(0.95 * len(ordered)) - 1))
    return ordered[index]


def _path_bytes(path: Path) -> int:
    if path.is_file():
        return int(path.stat().st_size)
    return sum(int(p.stat().st_size) for p in path.rglob("*") if p.is_file() and not p.is_symlink())


def _ocr_component(candidate_id: str) -> str:
    if candidate_id in {"ppocrv6-small-en", "ppocrv6-medium-en"}:
        return "ocr-en"
    if candidate_id in {"manga-ocr-ja", "ppocrv6-ja-fallback", "ppocrv6-medium-ja"}:
        return "ocr-ja"
    if candidate_id == "ppocrv5-ko":
        return "ocr-ko"
    if candidate_id in {"ppocrv6-small-zh", "ppocrv6-medium-zh"}:
        return "ocr-zh"
    raise BenchmarkExecutionError(f"unsupported OCR candidate: {candidate_id}")


def _component_languages(component: str) -> set[str]:
    return {
        "ocr-en": {"en"},
        "ocr-ja": {"ja"},
        "ocr-ko": {"ko"},
        "ocr-zh": {"zh-Hans", "zh-Hant"},
    }[component]


def _selected_ocr_key(language: str) -> str:
    return {"en": "ocrEnglish", "ja": "ocrJapanese", "ko": "ocrKorean", "zh-Hans": "ocrChinese", "zh-Hant": "ocrChinese"}[language]


def _process_peak_rss_mib() -> float:
    try:
        import resource
        value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        # macOS reports bytes; Linux/BSD commonly report KiB.
        if platform.system() == "Darwin":
            return value / (1024.0 * 1024.0)
        return value / 1024.0
    except (ImportError, AttributeError, OSError, ValueError):
        if os.name == "nt":
            try:
                import ctypes
                from ctypes import wintypes

                class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
                counters = PROCESS_MEMORY_COUNTERS()
                counters.cb = ctypes.sizeof(counters)
                handle = ctypes.windll.kernel32.GetCurrentProcess()
                if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                    return float(counters.PeakWorkingSetSize) / (1024.0 * 1024.0)
            except Exception:
                pass
    # Unknown memory must not look artificially excellent to a release gate.
    return 1.0e12


def _runtime_record() -> dict[str, str]:
    def version(distribution: str) -> str:
        try:
            return importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            return "not-installed"
    return {
        "pythonVersion": platform.python_version(),
        "os": platform.platform(),
        "cpu": platform.processor() or platform.machine() or "unknown",
        "gpu": os.environ.get("MTE_BENCHMARK_GPU", "none"),
        "hardwareClass": os.environ.get("MTE_BENCHMARK_HARDWARE_CLASS", "unclassified"),
        "paddlePaddleVersion": version("paddlepaddle"),
        "paddleOcrVersion": version("paddleocr"),
        "mangaOcrVersion": version("manga-ocr"),
        "torchVersion": version("torch"),
        "pillowVersion": version("pillow"),
        "onnxRuntimeVersion": version("onnxruntime"),
        "numpyVersion": version("numpy"),
        "transformersVersion": version("transformers"),
    }


def _load_review(path: Path) -> dict[str, Any]:
    try:
        review = require_dict(json.loads(path.read_text(encoding="utf-8")), label="benchmark review")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise BenchmarkExecutionError(f"cannot read benchmark review: {exc}") from exc
    expected = review.get("reviewRecordSha256")
    if not is_sha256(expected):
        raise BenchmarkExecutionError("benchmark review must be sealed with reviewRecordSha256")
    body = dict(review)
    body.pop("reviewRecordSha256", None)
    if sha256_bytes(canonical_json(body)) != expected:
        raise BenchmarkExecutionError("benchmark review content digest mismatch")
    return review


def _validate_review(review: dict[str, Any], *, run_plan: dict[str, Any], candidate_plan: dict[str, Any]) -> None:
    if review.get("schemaVersion") != 1 or review.get("reviewRevision") != "rev10-production-benchmark-review-v1":
        raise BenchmarkExecutionError("unsupported benchmark review schema/revision")
    if review.get("runPlanSha256") != run_plan.get("runPlanSha256"):
        raise BenchmarkExecutionError("benchmark review belongs to a different run plan")
    if not isinstance(review.get("reportId"), str) or not review["reportId"]:
        raise BenchmarkExecutionError("benchmark review reportId is required")
    inpaint = require_dict(review.get("inpaintingCandidates"), label="review.inpaintingCandidates")
    expected_inpaint = {item["candidateId"] for item in candidate_plan["candidates"] if item["component"] == "inpaint"}
    if set(inpaint) != expected_inpaint:
        raise BenchmarkExecutionError("benchmark review must exactly cover inpainting candidates")
    for candidate_id, raw in inpaint.items():
        item = require_dict(raw, label=f"review.inpaintingCandidates.{candidate_id}")
        pages = item.get("pagesReviewed")
        failures = item.get("criticalFailures")
        score = item.get("humanScore")
        if isinstance(pages, bool) or not isinstance(pages, int) or pages < 0:
            raise BenchmarkExecutionError("inpainting pagesReviewed must be a non-negative integer")
        if isinstance(failures, bool) or not isinstance(failures, int) or failures < 0:
            raise BenchmarkExecutionError("inpainting criticalFailures must be a non-negative integer")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0.0 <= float(score) <= 5.0 or not math.isfinite(float(score)):
            raise BenchmarkExecutionError("inpainting humanScore must be a finite value in 0..5")

    translation = require_dict(review.get("translation"), label="review.translation")
    for key in ("adapterId", "modelOrProviderRevision", "contextMode", "privacyMode"):
        if not isinstance(translation.get(key), str) or not translation[key]:
            raise BenchmarkExecutionError(f"review.translation.{key} is required")
    pages_reviewed = translation.get("pagesReviewed")
    critical = translation.get("criticalFailures")
    naturalness = translation.get("arabicNaturalnessMean")
    if isinstance(pages_reviewed, bool) or not isinstance(pages_reviewed, int) or pages_reviewed < 0:
        raise BenchmarkExecutionError("translation pagesReviewed must be a non-negative integer")
    if isinstance(critical, bool) or not isinstance(critical, int) or critical < 0:
        raise BenchmarkExecutionError("translation criticalFailures must be a non-negative integer")
    if isinstance(naturalness, bool) or not isinstance(naturalness, (int, float)) or not 0.0 <= float(naturalness) <= 5.0 or not math.isfinite(float(naturalness)):
        raise BenchmarkExecutionError("translation arabicNaturalnessMean must be a finite value in 0..5")
    by_language = require_dict(translation.get("pagesByLanguage"), label="review.translation.pagesByLanguage")
    expected_languages = {"en", "ja", "ko", "zh-Hans", "zh-Hant"}
    if set(by_language) != expected_languages:
        raise BenchmarkExecutionError("review.translation.pagesByLanguage must exactly cover V1 benchmark languages")
    for language, value in by_language.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise BenchmarkExecutionError(f"translation pagesByLanguage.{language} must be a non-negative integer")
    if sum(by_language.values()) > pages_reviewed:
        raise BenchmarkExecutionError("translation pagesByLanguage cannot exceed total pagesReviewed")

    renderer = require_dict(review.get("renderer"), label="review.renderer")
    for key in ("adapterRevision", "fontArtifactId", "goldenSuiteRevision"):
        if not isinstance(renderer.get(key), str) or not renderer[key]:
            raise BenchmarkExecutionError(f"review.renderer.{key} is required")
    for key in ("arabicRendererGoldensRun", "arabicRendererGoldensFailed"):
        value = renderer.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise BenchmarkExecutionError(f"review.renderer.{key} must be a non-negative integer")
    if renderer["arabicRendererGoldensFailed"] > renderer["arabicRendererGoldensRun"]:
        raise BenchmarkExecutionError("renderer failed golden count cannot exceed run count")


def seal_review_draft(draft: dict[str, Any]) -> dict[str, Any]:
    body = dict(draft)
    body.pop("reviewRecordSha256", None)
    body["reviewRecordSha256"] = sha256_bytes(canonical_json(body))
    return body


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
