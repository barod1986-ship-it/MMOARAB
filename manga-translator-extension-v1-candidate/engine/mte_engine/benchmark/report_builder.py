from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any

from .common import canonical_json, require_dict, require_list, sha256_bytes
from .metrics import aggregate_ocr, cer, detection_metrics, pairwise_order_accuracy
from .selection import select_winners

SUPPORTED_RAW_SCHEMA_VERSIONS = {1, 2}
REPORT_BUILDER_REVISION = "phase5b-report-builder-v4-executor-bound"


_DETECTION_COUNT_FIELDS = (
    "truePositive", "falsePositive", "falseNegative", "falseEraseCandidateCount",
    "criticalFalseEraseCount", "artworkFalsePositiveArea", "artworkArea",
    "maskOverreachPixels", "maskUndercoveragePixels", "groundTruthTextPixels",
)


def _rebuild_detection_from_page_rows(rows: list[Any]) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    if not rows:
        raise ValueError("detector execution pageRows must not be empty")
    aggregate = {field: 0 for field in _DETECTION_COUNT_FIELDS}
    by_language: dict[str, dict[str, int]] = {}
    seen_pages: set[str] = set()
    for index, raw_row in enumerate(rows):
        row = require_dict(raw_row, label=f"detectorPageRows[{index}]")
        page_id = row.get("pageId")
        language = row.get("language")
        if not isinstance(page_id, str) or not page_id or page_id in seen_pages:
            raise ValueError("detector execution pageRows require unique non-empty pageId values")
        seen_pages.add(page_id)
        if language not in {"en", "ja", "ko", "zh-Hans", "zh-Hant"}:
            raise ValueError("detector execution pageRows contain an unsupported language")
        counts = require_dict(row.get("counts"), label=f"detectorPageRows[{index}].counts")
        normalized_counts: dict[str, int] = {}
        for field in _DETECTION_COUNT_FIELDS:
            value = counts.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"detectorPageRows[{index}].counts.{field} must be a non-negative integer")
            normalized_counts[field] = value
            aggregate[field] += value
        lang_counts = by_language.setdefault(language, {field: 0 for field in _DETECTION_COUNT_FIELDS})
        for field, value in normalized_counts.items():
            lang_counts[field] += value
    return aggregate, by_language


def _detection_from_raw(raw: dict[str, Any]) -> dict[str, float | int]:
    return detection_metrics(
        true_positive=int(raw.get("truePositive", 0)),
        false_positive=int(raw.get("falsePositive", 0)),
        false_negative=int(raw.get("falseNegative", 0)),
        false_erase_candidates=int(raw.get("falseEraseCandidateCount", 0)),
        artwork_false_positive_area=int(raw.get("artworkFalsePositiveArea", 0)),
        artwork_area=int(raw.get("artworkArea", 0)),
        mask_overreach_pixels=int(raw.get("maskOverreachPixels", 0)),
        mask_undercoverage_pixels=int(raw.get("maskUndercoveragePixels", 0)),
        gt_text_pixels=int(raw.get("groundTruthTextPixels", 0)),
    )


def _normalized_detection(raw: dict[str, Any]) -> dict[str, float | int]:
    metrics = _detection_from_raw(raw)
    return {
        "dialogueRecall": metrics["recall"],
        "precision": metrics["precision"],
        "f1": metrics["f1"],
        "criticalFalseEraseCount": int(raw.get("criticalFalseEraseCount", 0)),
        "falseEraseCandidateCount": metrics["falseEraseCandidateCount"],
        "artworkFalsePositiveAreaRate": metrics["falsePositiveAreaOverArtworkRate"],
        "maskOverreachRate": metrics["maskOverreachRate"],
        "maskUndercoverageRate": metrics["maskUndercoverageRate"],
        "missedDialogueRegions": metrics["missedDialogueRegions"],
    }


def _normalize_sfx_rows(rows: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, raw_row in enumerate(rows):
        row = require_dict(raw_row, label=f"sfxRows[{index}]")
        page_id = row.get("pageId")
        block_id = row.get("blockId")
        language = row.get("language")
        kind = row.get("groundTruthKind")
        if not isinstance(page_id, str) or not page_id or len(page_id) > 128:
            raise ValueError(f"sfxRows[{index}].pageId must be a bounded non-empty string")
        if not isinstance(block_id, str) or not block_id or len(block_id) > 128:
            raise ValueError(f"sfxRows[{index}].blockId must be a bounded non-empty string")
        key = (page_id, block_id)
        if key in seen:
            raise ValueError("sfxRows may not contain duplicate pageId/blockId evidence")
        seen.add(key)
        if language not in {"en", "ja", "ko", "zh-Hans", "zh-Hant"}:
            raise ValueError(f"sfxRows[{index}].language is unsupported")
        if kind not in {"sfx", "uncertain"}:
            raise ValueError(f"sfxRows[{index}].groundTruthKind must be sfx or uncertain")
        protected = row.get("protectedFromEditing")
        sent = row.get("sentToTranslator")
        conflict = row.get("protectedConflictSilentOverwrite")
        if not isinstance(protected, bool) or not isinstance(sent, bool) or not isinstance(conflict, bool):
            raise ValueError(f"sfxRows[{index}] boolean evidence is malformed")
        integer_fields: dict[str, int] = {}
        for field in ("groundTruthPixels", "eraseInpaintOverlapPixels", "changedPixelsAfterEncodeDecode", "destructiveEditPixels"):
            value = row.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"sfxRows[{index}].{field} must be a non-negative integer")
            integer_fields[field] = value
        if kind == "sfx" and integer_fields["groundTruthPixels"] <= 0:
            raise ValueError(f"sfxRows[{index}].groundTruthPixels must be positive for SFX evidence")
        normalized.append({
            "pageId": page_id,
            "blockId": block_id,
            "language": language,
            "groundTruthKind": kind,
            "protectedFromEditing": protected,
            "sentToTranslator": sent,
            "protectedConflictSilentOverwrite": conflict,
            **integer_fields,
        })
    if not any(row["groundTruthKind"] == "sfx" for row in normalized):
        raise ValueError("sfxRows must include ground-truth SFX evidence")
    return normalized


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    index = min(len(ordered) - 1, max(0, math.ceil(0.95 * len(ordered)) - 1))
    return ordered[index]


def _schema2_projection(raw: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    execution = require_dict(raw.get("execution"), label="execution")
    machine = require_dict(execution.get("machineEvidence"), label="execution.machineEvidence")
    review = require_dict(execution.get("reviewSnapshot"), label="execution.reviewSnapshot")
    detector_evidence = require_dict(machine.get("detectorCandidates"), label="machineEvidence.detectorCandidates")
    ocr_evidence = require_dict(machine.get("ocrCandidates"), label="machineEvidence.ocrCandidates")
    inpaint_evidence = require_dict(machine.get("inpaintCandidates"), label="machineEvidence.inpaintCandidates")
    candidates: list[dict[str, Any]] = []
    for raw_candidate in require_list(raw.get("candidates"), label="candidates"):
        candidate = dict(require_dict(raw_candidate, label="candidate"))
        component = str(candidate.get("component", ""))
        candidate_id = str(candidate.get("candidateId", ""))
        if component == "detector":
            evidence = require_dict(detector_evidence.get(candidate_id), label=f"detectorEvidence.{candidate_id}")
            rebuilt_aggregate, _ = _rebuild_detection_from_page_rows(require_list(evidence.get("pageRows"), label=f"detectorEvidence.{candidate_id}.pageRows"))
            normalized = _normalized_detection(rebuilt_aggregate)
            candidate["metrics"] = {
                "dialogueRecall": normalized["dialogueRecall"],
                "precision": normalized["precision"],
                "f1": normalized["f1"],
                "criticalFalseEraseCount": normalized["criticalFalseEraseCount"],
                "artworkFalsePositiveAreaRate": normalized["artworkFalsePositiveAreaRate"],
                "p95Ms": _p95([float(v) for v in require_list(evidence.get("durationsMs"), label=f"detectorEvidence.{candidate_id}.durationsMs")]),
                "peakMemoryMiB": 0.0,
            }
        elif component.startswith("ocr-"):
            evidence = require_dict(ocr_evidence.get(candidate_id), label=f"ocrEvidence.{candidate_id}")
            rows = [require_dict(v, label=f"ocrEvidence.{candidate_id}.row") for v in require_list(evidence.get("rows"), label=f"ocrEvidence.{candidate_id}.rows")]
            if not rows:
                raise ValueError(f"OCR execution evidence is empty for {candidate_id}")
            candidate["metrics"] = {
                "cer": statistics.fmean(cer(str(row.get("reference", "")), str(row.get("prediction", ""))) for row in rows),
                "p95Ms": _p95([float(v) for v in require_list(evidence.get("durationsMs"), label=f"ocrEvidence.{candidate_id}.durationsMs")]),
                "modelBytes": int(evidence.get("modelBytes", -1)),
            }
        elif component == "inpaint":
            evidence = require_dict(inpaint_evidence.get(candidate_id), label=f"inpaintEvidence.{candidate_id}")
            review_entry = require_dict(require_dict(review.get("inpaintingCandidates"), label="review.inpaintingCandidates").get(candidate_id), label=f"review.inpaintingCandidates.{candidate_id}")
            candidate["metrics"] = {
                "humanCriticalFailures": int(review_entry.get("criticalFailures", -1)),
                "humanScore": float(review_entry.get("humanScore", -1)),
                "p95Ms": _p95([float(v) for v in require_list(evidence.get("durationsMs"), label=f"inpaintEvidence.{candidate_id}.durationsMs")]),
                "peakMemoryMiB": 0.0,
            }
        else:
            raise ValueError(f"Unsupported execution candidate component: {component}")
        candidates.append(candidate)
    selected = select_winners(candidates, policy)
    selected_detector = require_dict(detector_evidence.get(selected["detector"]), label="selected detector evidence")
    detection_raw, detection_by_language_raw = _rebuild_detection_from_page_rows(
        require_list(selected_detector.get("pageRows"), label="selected detector pageRows")
    )
    ocr_rows: list[dict[str, Any]] = []
    for key in ("ocrEnglish", "ocrJapanese", "ocrKorean", "ocrChinese"):
        evidence = require_dict(ocr_evidence.get(selected[key]), label=f"selected OCR evidence {key}")
        for row in require_list(evidence.get("rows"), label=f"selected OCR rows {key}"):
            value = require_dict(row, label="selected OCR row")
            ocr_rows.append({"language": value["language"], "reference": value["reference"], "prediction": value["prediction"]})
    selected_inpaint = require_dict(inpaint_evidence.get(selected["inpainter"]), label="selected inpaint evidence")
    clean_rows = [require_dict(v, label="cleanReferenceRow") for v in require_list(selected_inpaint.get("cleanReferenceRows"), label="selected inpaint cleanReferenceRows")]
    finite_psnr = [float(row["psnr"]) for row in clean_rows if math.isfinite(float(row["psnr"]))]
    translation_review = require_dict(review.get("translation"), label="review.translation")
    renderer_review = require_dict(review.get("renderer"), label="review.renderer")
    selected_inpaint_review = require_dict(require_dict(review.get("inpaintingCandidates"), label="review.inpaintingCandidates").get(selected["inpainter"]), label="review.selectedInpaintingCandidate")
    human_review = {
        "translationPagesReviewed": int(translation_review.get("pagesReviewed", 0)),
        "translationPagesByLanguage": dict(require_dict(translation_review.get("pagesByLanguage"), label="review.translation.pagesByLanguage")),
        "inpaintingPagesReviewed": int(selected_inpaint_review.get("pagesReviewed", 0)),
        "criticalTranslationFailures": int(translation_review.get("criticalFailures", 0)),
        "criticalInpaintingFailures": int(selected_inpaint_review.get("criticalFailures", 0)),
        "arabicNaturalnessMean": float(translation_review.get("arabicNaturalnessMean", 0.0)),
    }
    return {
        "candidates": candidates,
        "selected": selected,
        "detection": detection_raw,
        "detectionByLanguage": detection_by_language_raw,
        "ocrRows": ocr_rows,
        "readingOrderRows": require_list(machine.get("readingOrderRows"), label="machineEvidence.readingOrderRows"),
        "sfxRows": require_list(machine.get("sfxRows"), label="machineEvidence.sfxRows"),
        "qualityExtra": {
            "arabicRendererGoldensRun": int(renderer_review.get("arabicRendererGoldensRun", 0)),
            "arabicRendererGoldensFailed": int(renderer_review.get("arabicRendererGoldensFailed", 0)),
            "inpainting": {
                "cleanReferencePages": len(clean_rows),
                "mae": statistics.fmean(float(row["mae"]) for row in clean_rows) if clean_rows else None,
                "psnrMean": statistics.fmean(finite_psnr) if finite_psnr else None,
            },
        },
        "humanReview": human_review,
        "translation": {
            "adapterId": translation_review["adapterId"],
            "modelOrProviderRevision": translation_review["modelOrProviderRevision"],
            "contextMode": translation_review["contextMode"],
            "privacyMode": translation_review["privacyMode"],
            "roleClassifierRevision": "visual-enclosure-sfx-guard-v1",
        },
        "renderer": {
            "adapterRevision": renderer_review["adapterRevision"],
            "fontArtifactId": renderer_review["fontArtifactId"],
            "goldenSuiteRevision": renderer_review["goldenSuiteRevision"],
        },
        "performance": {
            "scope": str(machine.get("performanceScope", "")),
            "pageSeconds": require_list(machine.get("pageSeconds"), label="machineEvidence.pageSeconds"),
            "peakRamMiB": float(machine.get("peakRamMiB", 1.0e12)),
            "peakVramMiB": 0.0,
            "modelLoadSeconds": 0.0,
            "stageMs": {},
            "resultBytes": {},
        },
        "runtime": require_dict(execution.get("runtime"), label="execution.runtime"),
        "executionSummary": {
            "attestationRevision": execution.get("attestationRevision"),
            "executorRevision": execution.get("executorRevision"),
            "executorSourceSha256": execution.get("executorSourceSha256"),
            "reviewRecordSha256": execution.get("reviewRecordSha256"),
            "evidenceSha256": execution.get("evidenceSha256"),
        },
    }


def build_report(raw: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    if raw.get("schemaVersion") not in SUPPORTED_RAW_SCHEMA_VERSIONS:
        raise ValueError("Unsupported raw benchmark schemaVersion")
    if raw.get("schemaVersion") == 2:
        projected = _schema2_projection(raw, policy)
        candidates = projected["candidates"]
        selected = projected["selected"]
        detection_raw = projected["detection"]
        detection_by_language_raw = projected["detectionByLanguage"]
        sfx_source = projected["sfxRows"]
        reading_rows = projected["readingOrderRows"]
        performance_raw = projected["performance"]
        quality_extra = projected["qualityExtra"]
        human_review = projected["humanReview"]
        translation = projected["translation"]
        renderer = projected["renderer"]
        runtime = projected["runtime"]
        execution_summary = projected["executionSummary"]
        ocr_source = projected["ocrRows"]
    else:
        candidates = [require_dict(v, label="candidate") for v in require_list(raw.get("candidates"), label="candidates")]
        selected = select_winners(candidates, policy)
        detection_raw = require_dict(raw.get("detection"), label="detection")
        detection_by_language_raw = require_dict(raw.get("detectionByLanguage"), label="detectionByLanguage")
        sfx_source = require_list(raw.get("sfxRows"), label="sfxRows")
        reading_rows = require_list(raw.get("readingOrderRows"), label="readingOrderRows")
        performance_raw = require_dict(raw.get("performance"), label="performance")
        quality_extra = require_dict(raw.get("qualityExtra", {}), label="qualityExtra")
        human_review = raw["humanReview"]
        translation = raw["translation"]
        renderer = raw["renderer"]
        runtime = raw["runtime"]
        execution_summary = None
        ocr_source = require_list(raw.get("ocrRows"), label="ocrRows")
    detection_by_language = {
        language: _normalized_detection(require_dict(value, label=f"detectionByLanguage.{language}"))
        for language, value in sorted(detection_by_language_raw.items())
    }
    sfx_rows = _normalize_sfx_rows(list(sfx_source))
    sfx_only = [row for row in sfx_rows if row["groundTruthKind"] == "sfx"]
    uncertain_only = [row for row in sfx_rows if row["groundTruthKind"] == "uncertain"]
    sfx_pixels = sum(row["groundTruthPixels"] for row in sfx_only)
    if sfx_only and sfx_pixels <= 0:
        raise ValueError("sfxRows must contain positive groundTruthPixels for SFX blocks")
    sfx_denominator = max(1, len(sfx_only))
    sfx_pixel_denominator = max(1, sfx_pixels)
    uncertain_denominator = max(1, len(uncertain_only))
    sfx_pages_by_language: dict[str, set[str]] = defaultdict(set)
    for row in sfx_only:
        sfx_pages_by_language[row["language"]].add(row["pageId"])
    order_scores: list[float] = []
    order_by_language: dict[str, list[float]] = defaultdict(list)
    for raw_row in reading_rows:
        row = require_dict(raw_row, label="readingOrderRow")
        language = str(row.get("language", ""))
        score = pairwise_order_accuracy(list(row["reference"]), list(row["prediction"]))
        order_scores.append(score)
        order_by_language[language].append(score)
    page_seconds = [float(v) for v in require_list(performance_raw.get("pageSeconds"), label="performance.pageSeconds")]
    if not page_seconds:
        raise ValueError("performance.pageSeconds must not be empty")
    page_seconds.sort()
    p95_index = min(len(page_seconds) - 1, max(0, int((len(page_seconds) - 1) * 0.95 + 0.999999)))
    report = {
        "schemaVersion": 1,
        "reportId": raw["reportId"],
        "reportBuilderRevision": REPORT_BUILDER_REVISION,
        "rawBenchmarkSha256": sha256_bytes(canonical_json(raw)),
        "corpusId": raw["corpusId"],
        "corpusManifestSha256": raw["corpusManifestSha256"],
        "policyRevision": policy["policyRevision"],
        "candidatePlanSha256": raw.get("candidatePlanSha256"),
        "runPlanSha256": raw.get("runPlanSha256"),
        "execution": execution_summary,
        "runtime": runtime,
        "candidates": candidates,
        "selected": selected,
        "sfxSafety": {
            "sentToTranslatorRate": sum(1 for row in sfx_only if row["sentToTranslator"]) / sfx_denominator,
            "eraseInpaintMaskOverlapRate": sum(row["eraseInpaintOverlapPixels"] for row in sfx_only) / sfx_pixel_denominator,
            "changedPixelRateAfterEncodeDecode": sum(row["changedPixelsAfterEncodeDecode"] for row in sfx_only) / sfx_pixel_denominator,
            "uncertainDestructiveEditRate": sum(1 for row in uncertain_only if row["destructiveEditPixels"] > 0 or row["sentToTranslator"] or row["eraseInpaintOverlapPixels"] > 0) / uncertain_denominator,
            "protectedConflictSilentOverwriteCount": sum(1 for row in sfx_rows if row["protectedConflictSilentOverwrite"]),
            "independentGroundTruthPages": len({row["pageId"] for row in sfx_only}),
            "independentGroundTruthPagesByLanguage": {language: len(page_ids) for language, page_ids in sorted(sfx_pages_by_language.items())},
            "roleClassifierSfxProtectedRecall": sum(1 for row in sfx_only if row["protectedFromEditing"]) / sfx_denominator,
            "evidence": {
                "sfxBlocks": [{"pageId": row["pageId"], "blockId": row["blockId"], "language": row["language"]} for row in sfx_only],
                "uncertainBlocks": [{"pageId": row["pageId"], "blockId": row["blockId"], "language": row["language"]} for row in uncertain_only],
            },
        },
        "quality": {
            "detection": _normalized_detection(detection_raw),
            "detectionByLanguage": detection_by_language,
            "ocr": aggregate_ocr(ocr_source),
            "readingOrderPairwiseAccuracy": statistics.fmean(order_scores) if order_scores else 0.0,
            "readingOrderByLanguage": {
                language: {"pages": len(values), "pairwiseAccuracy": statistics.fmean(values)}
                for language, values in sorted(order_by_language.items())
            },
            "arabicRendererGoldensRun": int(quality_extra.get("arabicRendererGoldensRun", 0)),
            "arabicRendererGoldensFailed": int(quality_extra.get("arabicRendererGoldensFailed", 0)),
            "inpainting": quality_extra.get("inpainting", {}),
        },
        "humanReview": human_review,
        "translation": translation,
        "renderer": renderer,
        "performance": {
            "scope": str(performance_raw.get("scope", "legacy-unspecified")),
            "pageSamples": len(page_seconds),
            "p95PageSeconds": page_seconds[p95_index],
            "peakRamMiB": float(performance_raw.get("peakRamMiB", 0)),
            "peakVramMiB": float(performance_raw.get("peakVramMiB", 0)),
            "modelLoadSeconds": float(performance_raw.get("modelLoadSeconds", 0)),
            "meanPageSeconds": statistics.fmean(page_seconds),
            "stageMs": performance_raw.get("stageMs", {}),
            "resultBytes": performance_raw.get("resultBytes", {}),
        },
    }
    return report

