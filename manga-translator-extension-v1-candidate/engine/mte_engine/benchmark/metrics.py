from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable


def levenshtein(a: list[str], b: list[str]) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, left in enumerate(a, 1):
        current = [i]
        for j, right in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (left != right)))
        previous = current
    return previous[-1]


def cer(reference: str, prediction: str) -> float:
    ref = list(reference)
    if not ref:
        return 0.0 if not prediction else 1.0
    return levenshtein(ref, list(prediction)) / len(ref)


def wer(reference: str, prediction: str) -> float:
    ref = reference.split()
    if not ref:
        return 0.0 if not prediction.split() else 1.0
    return levenshtein(ref, prediction.split()) / len(ref)


def aggregate_ocr(rows: Iterable[dict[str, object]]) -> dict[str, object]:
    by_language: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        lang = str(row["language"])
        by_language[lang].append((cer(str(row["reference"]), str(row["prediction"])), wer(str(row["reference"]), str(row["prediction"]))))
    result: dict[str, object] = {}
    for lang, values in sorted(by_language.items()):
        result[lang] = {
            "samples": len(values),
            "cer": sum(v[0] for v in values) / len(values),
            "wer": sum(v[1] for v in values) / len(values),
        }
    return result


def detection_metrics(*, true_positive: int, false_positive: int, false_negative: int, false_erase_candidates: int, artwork_false_positive_area: int, artwork_area: int, mask_overreach_pixels: int, mask_undercoverage_pixels: int, gt_text_pixels: int) -> dict[str, float | int]:
    precision = true_positive / max(1, true_positive + false_positive)
    recall = true_positive / max(1, true_positive + false_negative)
    f1 = 2 * precision * recall / max(1e-12, precision + recall)
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "missedDialogueRegions": false_negative,
        "falseEraseCandidateCount": false_erase_candidates,
        "falsePositiveAreaOverArtworkRate": artwork_false_positive_area / max(1, artwork_area),
        "maskOverreachRate": mask_overreach_pixels / max(1, gt_text_pixels),
        "maskUndercoverageRate": mask_undercoverage_pixels / max(1, gt_text_pixels),
    }


def pairwise_order_accuracy(reference: list[str], prediction: list[str]) -> float:
    if set(reference) != set(prediction):
        return 0.0
    if len(reference) < 2:
        return 1.0
    ref_pos = {item: index for index, item in enumerate(reference)}
    pred_pos = {item: index for index, item in enumerate(prediction)}
    correct = total = 0
    for i, left in enumerate(reference):
        for right in reference[i + 1:]:
            total += 1
            if (ref_pos[left] < ref_pos[right]) == (pred_pos[left] < pred_pos[right]):
                correct += 1
    return correct / total


def psnr(*, mse: float, peak: float = 255.0) -> float:
    if mse <= 0:
        return math.inf
    return 20 * math.log10(peak) - 10 * math.log10(mse)
