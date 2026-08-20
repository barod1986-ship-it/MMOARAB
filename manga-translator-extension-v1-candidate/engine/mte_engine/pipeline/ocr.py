from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image

from ..errors import EngineApiError
from .contracts import DetectedRegion, OcrResult


ROUTING_REVISION = "ocr-freeze-runtime-v3-benchmark-selected-ja"
OCR_CANDIDATE_ARTIFACT = {
    "ppocrv6-small-en": "ppocrv6-small-rec",
    "ppocrv6-medium-en": "ppocrv6-medium-rec",
    "manga-ocr-ja": "manga-ocr-base-0.1.16",
    "ppocrv6-ja-fallback": "ppocrv6-medium-rec",  # historical candidate-plan v1/v2
    "ppocrv6-medium-ja": "ppocrv6-medium-rec",
    "ppocrv5-ko": "ppocrv5-korean-mobile-rec",
    "ppocrv6-small-zh": "ppocrv6-small-rec",
    "ppocrv6-medium-zh": "ppocrv6-medium-rec",
}


def route_for_language(source_language: str) -> tuple[str, ...]:
    if source_language == "en":
        return ("ppocrv6-en-benchmark-winner",)
    if source_language == "ja":
        return ("benchmark-frozen-japanese-winner",)
    if source_language == "ko":
        return ("korean-ppocrv5-mobile-rec",)
    if source_language in {"zh-Hans", "zh-Hant"}:
        return ("ppocrv6-zh-benchmark-winner",)
    if source_language == "auto":
        return ("script-probe", "language-primary", "single-fallback-on-qa-failure")
    return ("unsupported",)


class ReferenceOcrRouter:
    adapter_id = "reference-ocr-router-v1"

    def recognize(self, image: Image.Image, region: DetectedRegion, *, source_language: str) -> OcrResult:
        text = _sanitize_text(region.text_hint or "")
        confidence = 1.0 if text else 0.0
        return OcrResult(text=text, confidence=confidence, source_language=source_language if source_language != "auto" else "en", adapter_id=self.adapter_id)


class ProductionOcrRouter:
    """OCR router bound to the exact candidate IDs recorded in the production freeze."""

    adapter_id = ROUTING_REVISION

    def __init__(
        self,
        *,
        selected: dict[str, str],
        artifact_paths: dict[str, Path],
        paddle_factory: Callable[[Path], Any] | None = None,
        manga_factory: Callable[[Path], Any] | None = None,
    ) -> None:
        self.selected = dict(selected)
        self.artifact_paths = dict(artifact_paths)
        self._paddle_factory = paddle_factory or _default_paddle_recognizer_factory
        self._manga_factory = manga_factory or _default_manga_ocr_factory
        self._models: dict[tuple[str, str], Any] = {}

    def recognize(self, image: Image.Image, region: DetectedRegion, *, source_language: str) -> OcrResult:
        selected_key = _selection_key(source_language)
        candidate_id = self.selected.get(selected_key)
        if not candidate_id:
            raise EngineApiError("runtime_adapter_unavailable", f"Production OCR has no frozen candidate for {source_language}.", 409)
        artifact_id = OCR_CANDIDATE_ARTIFACT.get(candidate_id)
        if artifact_id is None:
            raise EngineApiError("runtime_adapter_unavailable", f"Frozen OCR candidate is not implemented: {candidate_id}.", 409)
        model_path = self.artifact_paths.get(artifact_id)
        if model_path is None or not model_path.exists():
            raise EngineApiError("model_not_ready", f"Frozen OCR artifact is missing: {artifact_id}.", 409)
        crop = _crop_region(image, region)
        if candidate_id == "manga-ocr-ja":
            return self._recognize_manga(crop, model_path, source_language)
        return self._recognize_paddle(crop, model_path, source_language, candidate_id)

    def _recognize_paddle(self, crop: Image.Image, model_path: Path, source_language: str, candidate_id: str) -> OcrResult:
        key = ("paddle", str(model_path))
        model = self._models.get(key)
        if model is None:
            try:
                model = self._paddle_factory(model_path)
            except EngineApiError:
                raise
            except Exception as exc:
                raise EngineApiError("runtime_adapter_unavailable", f"PaddleOCR recognizer could not initialize: {exc}", 409) from exc
            self._models[key] = model
        try:
            import numpy as np
        except ImportError as exc:
            raise EngineApiError("runtime_adapter_unavailable", "PaddleOCR recognizer requires numpy from the frozen production runtime.", 409) from exc
        try:
            rows = list(model.predict(input=np.asarray(crop.convert("RGB")), batch_size=1))
        except Exception as exc:
            raise EngineApiError("ocr_failed", f"Production OCR inference failed: {exc}", 502) from exc
        if not rows:
            return OcrResult("", 0.0, source_language, f"{self.adapter_id}:{candidate_id}")
        payload = _result_payload(rows[0])
        text = _sanitize_text(str(payload.get("rec_text", "")))
        try:
            confidence = float(payload.get("rec_score", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        if not 0.0 <= confidence <= 1.0:
            confidence = 0.0
        return OcrResult(text, confidence, source_language, f"{self.adapter_id}:{candidate_id}")

    def _recognize_manga(self, crop: Image.Image, model_path: Path, source_language: str) -> OcrResult:
        key = ("manga", str(model_path))
        model = self._models.get(key)
        if model is None:
            try:
                model = self._manga_factory(model_path)
            except EngineApiError:
                raise
            except Exception as exc:
                raise EngineApiError("runtime_adapter_unavailable", f"manga-ocr could not initialize: {exc}", 409) from exc
            self._models[key] = model
        try:
            text = _sanitize_text(str(model(crop.convert("RGB"))))
        except Exception as exc:
            raise EngineApiError("ocr_failed", f"manga-ocr inference failed: {exc}", 502) from exc
        # manga-ocr's public callable returns text, not a native confidence score. 0.5 is
        # deliberately neutral rather than pretending a probability; release quality is
        # controlled by the independently frozen CER benchmark and the common text QA.
        confidence = 0.5 if text else 0.0
        return OcrResult(text, confidence, source_language, f"{self.adapter_id}:manga-ocr-ja:no-native-score")


def production_ocr_candidates_supported(selected: dict[str, str]) -> tuple[bool, str | None]:
    for key in ("ocrEnglish", "ocrJapanese", "ocrKorean", "ocrChinese"):
        candidate = selected.get(key)
        if not isinstance(candidate, str) or candidate not in OCR_CANDIDATE_ARTIFACT:
            return False, f"unsupported frozen OCR candidate for {key}: {candidate!r}"
    return True, None


def _selection_key(source_language: str) -> str:
    if source_language == "en":
        return "ocrEnglish"
    if source_language == "ja":
        return "ocrJapanese"
    if source_language == "ko":
        return "ocrKorean"
    if source_language in {"zh-Hans", "zh-Hant"}:
        return "ocrChinese"
    raise EngineApiError("unsupported_language", f"Production OCR does not accept sourceLanguage={source_language!r} in V1; choose an explicit supported language.", 400)


def _default_paddle_recognizer_factory(model_path: Path) -> Any:
    try:
        from paddleocr import TextRecognition
    except ImportError as exc:
        raise EngineApiError("runtime_adapter_unavailable", "Frozen production OCR requires PaddleOCR.", 409) from exc
    if not model_path.is_dir():
        raise EngineApiError("model_not_ready", "PaddleOCR runtime requires a materialized local recognition-model directory.", 409)
    return TextRecognition(model_dir=str(model_path), device="cpu")


def _default_manga_ocr_factory(model_path: Path) -> Any:
    try:
        from manga_ocr import MangaOcr
    except ImportError as exc:
        raise EngineApiError("runtime_adapter_unavailable", "Frozen Japanese OCR requires manga-ocr.", 409) from exc
    if not model_path.is_dir():
        raise EngineApiError("model_not_ready", "manga-ocr runtime requires a materialized local model directory.", 409)
    return MangaOcr(pretrained_model_name_or_path=str(model_path), force_cpu=True)


def _crop_region(image: Image.Image, region: DetectedRegion) -> Image.Image:
    xs = [point[0] for point in region.polygon]
    ys = [point[1] for point in region.polygon]
    left = max(0, min(xs) - 2)
    top = max(0, min(ys) - 2)
    right = min(image.width, max(xs) + 3)
    bottom = min(image.height, max(ys) + 3)
    if right <= left or bottom <= top:
        raise EngineApiError("ocr_failed", "Detected OCR region is empty after clipping.", 502)
    return image.crop((left, top, right, bottom))


def _result_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value.get("res") if isinstance(value.get("res"), dict) else value
    for name in ("json", "res"):
        candidate = getattr(value, name, None)
        if callable(candidate):
            candidate = candidate()
        if isinstance(candidate, dict):
            return candidate.get("res") if isinstance(candidate.get("res"), dict) else candidate
    raise EngineApiError("ocr_failed", "OCR backend returned an unsupported result shape.", 502)


def ocr_qa(result: OcrResult, *, source_language: str) -> bool:
    text = result.text.strip()
    if not text or result.confidence < 0.35:
        return False
    if "\ufffd" in text or any(ord(char) < 32 and char not in "\n\t" for char in text):
        return False
    if re.search(r"(.)\1{10,}", text):
        return False
    if source_language == "en":
        visible = [char for char in text if char.isalpha()]
        if visible and sum(char.isascii() for char in visible) / len(visible) < 0.7:
            return False
    return True


def _sanitize_text(value: str) -> str:
    value = value.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    return " ".join(value.split())[:4096]
