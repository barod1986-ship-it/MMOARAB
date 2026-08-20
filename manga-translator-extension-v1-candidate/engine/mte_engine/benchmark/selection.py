from __future__ import annotations

from typing import Any

from .common import require_dict

COMPONENT_TO_SELECTED_KEY = {
    "detector": "detector",
    "ocr-en": "ocrEnglish",
    "ocr-ja": "ocrJapanese",
    "ocr-ko": "ocrKorean",
    "ocr-zh": "ocrChinese",
    "inpaint": "inpainter",
}
OCR_COMPONENT_LANG = {"ocr-en": "en", "ocr-ja": "ja", "ocr-ko": "ko", "ocr-zh": "zh-Hans"}


class SelectionError(ValueError):
    pass


def select_winners(candidates: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, str]:
    grouped: dict[str, list[dict[str, Any]]] = {component: [] for component in COMPONENT_TO_SELECTED_KEY}
    for candidate in candidates:
        component = candidate.get("component")
        if component in grouped:
            grouped[str(component)].append(candidate)
    selected: dict[str, str] = {}
    for component, values in grouped.items():
        if not values:
            raise SelectionError(f"No candidates were benchmarked for {component}")
        if component == "detector":
            winner = _select_detector(values, policy)
        elif component == "inpaint":
            winner = _select_inpaint(values, policy)
        else:
            winner = _select_ocr(component, values, policy)
        selected[COMPONENT_TO_SELECTED_KEY[component]] = str(winner["candidateId"])
    return selected


def _metrics(candidate: dict[str, Any]) -> dict[str, Any]:
    return require_dict(candidate.get("metrics"), label=f"{candidate.get('candidateId')}.metrics")


def _select_detector(values: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
    thresholds = require_dict(policy["qualityThresholds"], label="qualityThresholds")
    eligible = []
    for item in values:
        m = _metrics(item)
        if (
            int(m.get("criticalFalseEraseCount", 1)) == 0
            and float(m.get("dialogueRecall", 0)) >= float(thresholds["dialogueRecallMin"])
            and float(m.get("precision", 0)) >= float(thresholds["detectionPrecisionMin"])
            and float(m.get("artworkFalsePositiveAreaRate", 1)) <= float(thresholds["artworkFalsePositiveAreaRateMax"])
        ):
            eligible.append(item)
    if not eligible:
        raise SelectionError("No detector candidate clears the hard release floors")
    return min(
        eligible,
        key=lambda item: (
            -float(_metrics(item).get("dialogueRecall", 0)),
            -float(_metrics(item).get("f1", 0)),
            float(_metrics(item).get("p95Ms", 1e18)),
            float(_metrics(item).get("peakMemoryMiB", 1e18)),
            str(item["candidateId"]),
        ),
    )


def _select_ocr(component: str, values: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
    thresholds = require_dict(policy["qualityThresholds"], label="qualityThresholds")
    limits = require_dict(thresholds["ocrCerMax"], label="ocrCerMax")
    language = OCR_COMPONENT_LANG[component]
    limit = float(limits[language])
    eligible = [item for item in values if float(_metrics(item).get("cer", 1)) <= limit]
    if not eligible:
        raise SelectionError(f"No {component} candidate clears the CER release floor")
    best_quality = min(eligible, key=lambda item: (float(_metrics(item)["cer"]), float(_metrics(item).get("p95Ms", 1e18)), str(item["candidateId"])))
    best_m = _metrics(best_quality)
    near = []
    for item in eligible:
        m = _metrics(item)
        if (
            float(m["cer"]) <= float(best_m["cer"]) + 0.005
            and float(m.get("p95Ms", 1e18)) <= float(best_m.get("p95Ms", 1e18)) * 0.85
            and int(m.get("modelBytes", 2**63 - 1)) < int(best_m.get("modelBytes", 2**63 - 1))
        ):
            near.append(item)
    if near:
        return min(near, key=lambda item: (int(_metrics(item).get("modelBytes", 2**63 - 1)), float(_metrics(item).get("p95Ms", 1e18)), float(_metrics(item)["cer"]), str(item["candidateId"])))
    return best_quality


def _select_inpaint(values: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
    threshold = float(require_dict(policy["qualityThresholds"], label="qualityThresholds")["inpaintingHumanScoreMin"])
    eligible = [
        item for item in values
        if int(_metrics(item).get("humanCriticalFailures", 1)) == 0 and float(_metrics(item).get("humanScore", 0)) >= threshold
    ]
    if not eligible:
        raise SelectionError("No inpainting candidate clears the human-review safety/quality floor")
    return min(
        eligible,
        key=lambda item: (
            -float(_metrics(item).get("humanScore", 0)),
            float(_metrics(item).get("p95Ms", 1e18)),
            float(_metrics(item).get("peakMemoryMiB", 1e18)),
            str(item["candidateId"]),
        ),
    )
