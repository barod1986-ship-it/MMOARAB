from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

from PIL import Image

from ..errors import EngineApiError
from .contracts import DetectedRegion, LayoutMode

DETECTOR_SELECTION_REVISION = "detector-freeze-runtime-v3"
PADDLE_DETECTOR_CANDIDATES = {
    # Current V1 candidate-plan-v2 IDs.
    "ppocrv6-small-detector-run": "ppocrv6-small-det",
    "ppocrv6-medium-detector-run": "ppocrv6-medium-det",
    # Legacy pre-v2 candidate ID retained only so an old local benchmark freeze
    # fails or runs deterministically rather than being silently remapped.
    "ppocrv6-detector-run": "ppocrv6-medium-det",
}
MAX_DETECTED_REGIONS = 512


class ReferenceDetector:
    adapter_id = "reference-fixture-detector-v1"

    def __init__(self, regions: Sequence[DetectedRegion] = ()) -> None:
        self._regions = tuple(regions)

    def detect(self, image: Image.Image, *, source_language: str, layout_mode: LayoutMode) -> Sequence[DetectedRegion]:
        return self._regions


class ProductionDetector:
    """Freeze-selected production text detector.

    V1 supports the release-qualified PaddleOCR small/medium detector candidates.
    The exact winner and local artifact must be benchmarked and hash-pinned. Unsupported winners fail closed;
    no network model lookup or implicit model substitution is allowed here.
    """

    adapter_id = DETECTOR_SELECTION_REVISION

    def __init__(
        self,
        *,
        candidate_id: str,
        model_path: Path,
        model_factory: Callable[[Path], Any] | None = None,
    ) -> None:
        if candidate_id not in PADDLE_DETECTOR_CANDIDATES:
            raise EngineApiError(
                "runtime_adapter_unavailable",
                f"Frozen detector candidate is not implemented by this Engine build: {candidate_id}.",
                409,
            )
        if not model_path.exists():
            raise EngineApiError("model_not_ready", "Frozen detector artifact is missing.", 409)
        self.candidate_id = candidate_id
        self.model_path = model_path
        self._model_factory = model_factory or _default_paddle_detector_factory
        self._model: Any | None = None

    def _get_model(self) -> Any:
        if self._model is None:
            try:
                self._model = self._model_factory(self.model_path)
            except EngineApiError:
                raise
            except Exception as exc:  # dependency/backend errors are normalized at the boundary
                raise EngineApiError("runtime_adapter_unavailable", f"PaddleOCR detector could not initialize: {exc}", 409) from exc
        return self._model

    def detect(self, image: Image.Image, *, source_language: str, layout_mode: LayoutMode) -> Sequence[DetectedRegion]:
        try:
            import numpy as np  # PaddleOCR production dependency; never auto-installed.
        except ImportError as exc:
            raise EngineApiError("runtime_adapter_unavailable", "PaddleOCR detector requires numpy from the frozen production runtime.", 409) from exc
        model = self._get_model()
        try:
            output = model.predict(input=np.asarray(image.convert("RGB")), batch_size=1)
            rows = list(output) if not isinstance(output, list) else output
        except Exception as exc:
            raise EngineApiError("detection_failed", f"Production detector inference failed: {exc}", 502) from exc
        if not rows:
            return ()
        payload = _result_payload(rows[0])
        polygons = payload.get("dt_polys")
        scores = payload.get("dt_scores")
        if polygons is None:
            raise EngineApiError("detection_failed", "PaddleOCR detector result omitted dt_polys.", 502)
        polygon_rows = _as_rows(polygons)
        score_rows = _as_scores(scores, len(polygon_rows))
        regions: list[DetectedRegion] = []
        for index, (raw_polygon, score) in enumerate(zip(polygon_rows, score_rows, strict=True)):
            polygon = _normalize_polygon(raw_polygon, image.width, image.height)
            if polygon is None:
                continue
            xs = [point[0] for point in polygon]
            ys = [point[1] for point in polygon]
            orientation = "horizontal" if (max(xs) - min(xs)) >= (max(ys) - min(ys)) else "vertical"
            regions.append(
                DetectedRegion(
                    region_id=f"det-{index:04d}",
                    polygon=polygon,
                    confidence=score,
                    orientation_hint=orientation,
                )
            )
        # A malicious/degenerate detector result cannot inflate later work without bound.
        if len(regions) > MAX_DETECTED_REGIONS:
            regions = sorted(regions, key=lambda item: (-item.confidence, item.region_id))[:MAX_DETECTED_REGIONS]
        return tuple(regions)


def _default_paddle_detector_factory(model_path: Path) -> Any:
    try:
        from paddleocr import TextDetection
    except ImportError as exc:
        raise EngineApiError("runtime_adapter_unavailable", "Frozen production detector requires PaddleOCR.", 409) from exc
    if not model_path.is_dir():
        raise EngineApiError(
            "model_not_ready",
            "PaddleOCR runtime requires the frozen detector artifact to be materialized as a local model directory.",
            409,
        )
    # CPU is the portable V1 execution target. A future GPU profile needs a distinct
    # benchmark/runtime revision rather than silently changing execution semantics.
    return TextDetection(model_dir=str(model_path), device="cpu")


def _result_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        if isinstance(value.get("res"), dict):
            return value["res"]
        return value
    for name in ("json", "res"):
        candidate = getattr(value, name, None)
        if callable(candidate):
            candidate = candidate()
        if isinstance(candidate, dict):
            if isinstance(candidate.get("res"), dict):
                return candidate["res"]
            return candidate
    raise EngineApiError("detection_failed", "PaddleOCR detector returned an unsupported result shape.", 502)


def _as_rows(value: Any) -> list[Any]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, dict)):
        raise EngineApiError("detection_failed", "PaddleOCR dt_polys is malformed.", 502)
    return list(value)


def _as_scores(value: Any, count: int) -> list[float]:
    if value is None:
        return [1.0] * count
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, dict)):
        raise EngineApiError("detection_failed", "PaddleOCR dt_scores is malformed.", 502)
    scores = list(value)
    if len(scores) != count:
        raise EngineApiError("detection_failed", "PaddleOCR detector returned mismatched polygon/score counts.", 502)
    normalized: list[float] = []
    for raw in scores:
        try:
            score = float(raw)
        except (TypeError, ValueError) as exc:
            raise EngineApiError("detection_failed", "PaddleOCR detector score is malformed.", 502) from exc
        if not 0.0 <= score <= 1.0:
            raise EngineApiError("detection_failed", "PaddleOCR detector score is outside 0..1.", 502)
        normalized.append(score)
    return normalized


def _normalize_polygon(raw: Any, width: int, height: int) -> tuple[tuple[int, int], ...] | None:
    if hasattr(raw, "tolist"):
        raw = raw.tolist()
    if not isinstance(raw, (list, tuple)) or not 3 <= len(raw) <= 16:
        return None
    points: list[tuple[int, int]] = []
    for pair in raw:
        if hasattr(pair, "tolist"):
            pair = pair.tolist()
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            return None
        try:
            x = int(round(float(pair[0])))
            y = int(round(float(pair[1])))
        except (TypeError, ValueError):
            return None
        x = min(max(x, 0), width - 1)
        y = min(max(y, 0), height - 1)
        points.append((x, y))
    if len(set(points)) < 3:
        return None
    return tuple(points)
