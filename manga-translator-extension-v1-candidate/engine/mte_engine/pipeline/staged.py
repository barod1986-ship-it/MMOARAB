from __future__ import annotations

import hashlib
import io
import json
import time
from dataclasses import dataclass
from collections.abc import Callable

from PIL import Image, ImageChops, ImageOps, UnidentifiedImageError

from ..constants import HARD_EXECUTION_SECONDS, MAX_DECODED_PIXELS, MAX_RESULT_BYTES
from ..errors import EngineApiError
from .contracts import (
    BlockRoleClassifier,
    DetectorAdapter,
    EngineTextBlock,
    InpainterAdapter,
    LayoutMode,
    OcrRouter,
    ReadingOrderAdapter,
    RendererAdapter,
    TranslationInputBlock,
    TranslatorAdapter,
)
from .manifest import MAX_MANIFEST_JSON_BYTES, build_manifest, validate_manifest
from .masks import build_erase_mask, build_protected_mask
from .ocr import ocr_qa

_ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "AVIF"}
_ALLOWED_MODES = {"1", "L", "LA", "P", "RGB", "RGBA", "CMYK"}
STAGE_NAMES = ("decode", "detect", "order", "ocr", "translate", "mask", "inpaint", "typeset", "composite", "encode")


@dataclass(frozen=True, slots=True)
class PipelineArtifact:
    encoded: bytes
    mime: str
    sha256: str
    width: int
    height: int
    manifest: dict[str, object]


class StagedPipeline:
    def __init__(
        self,
        *,
        detector: DetectorAdapter,
        reading_order: ReadingOrderAdapter,
        ocr: OcrRouter,
        roles: BlockRoleClassifier,
        translator: TranslatorAdapter,
        inpainter: InpainterAdapter,
        renderer: RendererAdapter,
    ) -> None:
        self.detector = detector
        self.reading_order = reading_order
        self.ocr = ocr
        self.roles = roles
        self.translator = translator
        self.inpainter = inpainter
        self.renderer = renderer

    def process(
        self,
        source_path,
        *,
        job_id: str,
        profile_fingerprint: str,
        source_language: str,
        target_language: str,
        layout_mode: LayoutMode = "auto",
        stage_callback: Callable[[str, int, int], None] | None = None,
        started_at: float | None = None,
    ) -> PipelineArtifact:
        started = started_at or time.monotonic()
        total = len(STAGE_NAMES)

        def stage(name: str) -> None:
            _check_budget(started)
            if stage_callback:
                stage_callback(name, STAGE_NAMES.index(name), total)

        stage("decode")
        normalized = _decode(source_path)
        source_pixels = normalized.copy()

        stage("detect")
        regions = list(self.detector.detect(normalized, source_language=source_language, layout_mode=layout_mode))
        _validate_regions(regions, normalized.size)

        stage("order")
        ordered = list(self.reading_order.order(regions, image_size=normalized.size, source_language=source_language, layout_mode=layout_mode))
        _validate_order_identity(regions, ordered)

        stage("ocr")
        blocks: list[EngineTextBlock] = []
        for index, region in enumerate(ordered):
            result = self.ocr.recognize(normalized, region, source_language=source_language)
            accepted = ocr_qa(result, source_language=source_language)
            if not accepted:
                # Weak OCR evidence cannot unlock destructive editing.
                result = type(result)(text=result.text, confidence=min(result.confidence, 0.34), source_language=result.source_language, adapter_id=result.adapter_id)
            decision = self.roles.classify(normalized, region, result) if accepted else self.roles.classify(normalized, type(region)(
                region.region_id, region.polygon, region.confidence, region.orientation_hint, region.text_hint, "uncertain", region.style_hints
            ), result)
            block = EngineTextBlock(
                block_id=_stable_block_id(region.polygon, index),
                polygon=region.polygon,
                reading_order=index,
                source_text=result.text,
                source_confidence=result.confidence,
                source_language=result.source_language,
                block_kind=decision.block_kind,
                processing_action=decision.processing_action,
                protected_from_editing=decision.protected_from_editing,
                style_hints=region.style_hints,
            )
            blocks.append(block)

        stage("translate")
        eligible = [block for block in blocks if block.processing_action == "translate-replace" and block.source_text.strip()]
        translations = self.translator.translate_page(
            source_language=source_language,
            target_language=target_language,
            blocks=[TranslationInputBlock(block.block_id, block.source_text) for block in eligible],
        ) if eligible else []
        by_id = {item.block_id: item.text.strip() for item in translations}
        if set(by_id) != {block.block_id for block in eligible} or any(not value for value in by_id.values()):
            raise EngineApiError("translation_failed", "Translator must return one non-empty translation for every requested block ID and no extras.", 502)
        for block in eligible:
            block.target_text = by_id[block.block_id]
            block.target_language = target_language

        stage("mask")
        protected_mask = build_protected_mask(normalized.size, blocks)
        erase_mask = build_erase_mask(normalized.size, blocks, protected_mask)

        stage("inpaint")
        working = self.inpainter.inpaint(normalized, erase_mask) if erase_mask.getbbox() is not None else normalized.copy()
        if working.size != normalized.size:
            raise EngineApiError("inpaint_failed", "Inpainter changed source dimensions.", 500)

        stage("typeset")
        rendered = self.renderer.render(working, blocks, protected_mask=protected_mask) if eligible else working

        stage("composite")
        # Protected source-pixel composite is the final authority before encoding.
        rendered.paste(source_pixels, (0, 0), protected_mask)

        manifest = build_manifest(job_id=job_id, profile_fingerprint=profile_fingerprint, blocks=blocks)
        validate_manifest(manifest, width=rendered.width, height=rendered.height)
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(manifest_bytes) > MAX_MANIFEST_JSON_BYTES:
            raise EngineApiError("invalid_result", "Result manifest exceeds the V1 size bound.", 500)

        stage("encode")
        encoded, mime = _encode_exact_lossless(rendered)
        decoded = _decode_bytes(encoded)
        if _has_pixel_difference(rendered, decoded):
            raise EngineApiError("invalid_result", "Exact-lossless encoder verification failed.", 500)
        _verify_protected_pixels(source_pixels, decoded, protected_mask)
        return PipelineArtifact(
            encoded=encoded,
            mime=mime,
            sha256="sha256:" + hashlib.sha256(encoded).hexdigest(),
            width=rendered.width,
            height=rendered.height,
            manifest=manifest,
        )


def _decode(source_path) -> Image.Image:
    try:
        with Image.open(source_path) as source:
            if source.format not in _ALLOWED_FORMATS:
                raise EngineApiError("unsupported_image_format", "Source image container is not supported by Engine V1.", 415)
            if getattr(source, "n_frames", 1) != 1:
                raise EngineApiError("unsupported_image_format", "Animated images are not supported by Engine V1.", 415)
            width, height = source.size
            pixels = width * height
            if width <= 0 or height <= 0 or pixels > MAX_DECODED_PIXELS:
                raise EngineApiError("decoded_image_too_large", "Decoded image exceeds the V1 pixel guard.", 413, details={"pixels": pixels})
            if source.mode not in _ALLOWED_MODES:
                raise EngineApiError("unsupported_pixel_format", "Source pixel format is not supported safely by Engine V1.", 415)
            source.load()
            return ImageOps.exif_transpose(source).convert("RGBA")
    except EngineApiError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise EngineApiError("decode_failed", "Source raster could not be decoded safely.", 400) from exc


def _encode_exact_lossless(image: Image.Image) -> tuple[bytes, str]:
    webp = io.BytesIO()
    try:
        image.save(webp, format="WEBP", lossless=True, quality=100, method=6, exact=True, exif=b"", xmp=b"")
    except (OSError, ValueError):
        webp = io.BytesIO()
    payload = webp.getvalue()
    if payload and len(payload) <= MAX_RESULT_BYTES and not _has_pixel_difference(image, _decode_bytes(payload)):
        return payload, "image/webp"
    png = io.BytesIO()
    try:
        image.save(png, format="PNG", optimize=True)
    except (OSError, ValueError) as exc:
        raise EngineApiError("encode_failed", "PNG rescue encoding failed.", 500) from exc
    payload = png.getvalue()
    if len(payload) <= MAX_RESULT_BYTES and not _has_pixel_difference(image, _decode_bytes(payload)):
        return payload, "image/png"
    raise EngineApiError("result_too_large", "No exact-lossless V1 result fits within 32 MiB.", 413)


def _decode_bytes(payload: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(payload)) as decoded:
            decoded.load()
            return decoded.convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise EngineApiError("invalid_result", "Encoded result could not be decoded for validation.", 500) from exc


def _verify_protected_pixels(source: Image.Image, result: Image.Image, protected_mask: Image.Image) -> None:
    if protected_mask.getbbox() is None:
        return
    source_crop = Image.composite(source, Image.new("RGBA", source.size, (0, 0, 0, 0)), protected_mask)
    result_crop = Image.composite(result, Image.new("RGBA", result.size, (0, 0, 0, 0)), protected_mask)
    if _has_pixel_difference(source_crop, result_crop):
        raise EngineApiError("invalid_result", "Protected SFX/uncertain source pixels changed after final encode/decode.", 500)


def _has_pixel_difference(a: Image.Image, b: Image.Image) -> bool:
    if a.size != b.size or a.mode != b.mode:
        return True
    extrema = ImageChops.difference(a, b).getextrema()
    if isinstance(extrema[0], tuple):
        return any(high != 0 for _, high in extrema)
    return extrema[1] != 0


def _validate_regions(regions, size: tuple[int, int]) -> None:
    width, height = size
    if len(regions) > 512:
        raise EngineApiError("detection_failed", "Detector returned too many text regions.", 500)
    ids: set[str] = set()
    for region in regions:
        if not region.region_id or region.region_id in ids or not 3 <= len(region.polygon) <= 16 or not 0 <= region.confidence <= 1:
            raise EngineApiError("detection_failed", "Detector returned malformed region metadata.", 500)
        ids.add(region.region_id)
        for x, y in region.polygon:
            if not 0 <= x < width or not 0 <= y < height:
                raise EngineApiError("detection_failed", "Detector region leaves image bounds.", 500)


def _validate_order_identity(before, after) -> None:
    if len(before) != len(after) or {item.region_id for item in before} != {item.region_id for item in after}:
        raise EngineApiError("reading_order_failed", "Reading-order adapter changed detector membership.", 500)


def _stable_block_id(polygon, order: int) -> str:
    canonical = json.dumps([order, [[int(x), int(y)] for x, y in polygon]], separators=(",", ":"))
    return "b-" + hashlib.sha256(canonical.encode("ascii")).hexdigest()[:16]


def _check_budget(started: float) -> None:
    if time.monotonic() - started > HARD_EXECUTION_SECONDS:
        raise EngineApiError("engine_timeout", "Engine pipeline exceeded the hard execution budget.", 500, retryable=True)
