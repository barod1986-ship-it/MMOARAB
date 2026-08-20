from __future__ import annotations

import hashlib
from pathlib import Path
from collections.abc import Sequence

from PIL import Image, ImageDraw, ImageFont, features

from ..errors import EngineApiError
from .contracts import EngineTextBlock
from .masks import ensure_render_regions_do_not_overlap_protected

RENDERER_REVISION = "pillow-raqm-v1"
LAYOUT_REVISION = "arabic-word-fit-binary-search-v1"


class ArabicRenderer:
    adapter_id = RENDERER_REVISION

    def __init__(self, font_path: Path, *, min_size: int = 10, max_size: int = 72) -> None:
        self.font_path = font_path
        self.min_size = min_size
        self.max_size = max_size
        if not font_path.is_file():
            raise EngineApiError("renderer_capability_missing", "Configured Arabic font artifact is missing.", 409)
        if not features.check("raqm"):
            raise EngineApiError("renderer_capability_missing", "Pillow libraqm support is required for Arabic shaping and bidi.", 409)

    @property
    def font_sha256(self) -> str:
        digest = hashlib.sha256()
        with self.font_path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return "sha256:" + digest.hexdigest()

    def self_test(self) -> None:
        canvas = Image.new("RGBA", (480, 180), "white")
        draw = ImageDraw.Draw(canvas)
        font = ImageFont.truetype(str(self.font_path), 34, layout_engine=ImageFont.Layout.RAQM)
        sample = "العربية لا 123 (اختبار) Arabic + 123 + English"
        try:
            bbox = draw.textbbox((240, 90), sample, font=font, anchor="mm", direction="rtl", language="ar")
            draw.text((240, 90), sample, fill="black", font=font, anchor="mm", direction="rtl", language="ar")
        except (KeyError, ValueError, OSError) as exc:
            raise EngineApiError("renderer_capability_missing", "Arabic RAQM renderer self-test failed.", 409) from exc
        if bbox[2] <= bbox[0] or bbox[3] <= bbox[1] or canvas.getbbox() is None:
            raise EngineApiError("renderer_capability_missing", "Arabic RAQM renderer self-test produced no measurable output.", 409)

    def render(self, image: Image.Image, blocks: Sequence[EngineTextBlock], *, protected_mask: Image.Image) -> Image.Image:
        ensure_render_regions_do_not_overlap_protected(blocks, protected_mask)
        result = image.convert("RGBA").copy()
        draw = ImageDraw.Draw(result)
        for block in blocks:
            if block.processing_action != "translate-replace" or not block.target_text:
                continue
            left, top, right, bottom = _bounds(block)
            if right - left < 8 or bottom - top < 8:
                raise EngineApiError("render_failed", "Text region is too small for safe Arabic rendering.", 409)
            lines, font = self._fit(draw, block.target_text, (right - left - 6, bottom - top - 6))
            line_height = max(1, int(font.size * 1.25))
            total_height = line_height * len(lines)
            y = top + max(3, ((bottom - top) - total_height) // 2)
            center_x = (left + right) // 2
            for line in lines:
                draw.text(
                    (center_x, y),
                    line,
                    font=font,
                    fill=block.style_hints.foreground,
                    stroke_width=max(1, font.size // 18),
                    stroke_fill=block.style_hints.outline,
                    anchor="ma",
                    direction="rtl",
                    language="ar",
                )
                y += line_height
        return result

    def _fit(self, draw: ImageDraw.ImageDraw, text: str, box: tuple[int, int]) -> tuple[list[str], ImageFont.FreeTypeFont]:
        width, height = box
        lo, hi = self.min_size, self.max_size
        best: tuple[list[str], ImageFont.FreeTypeFont] | None = None
        while lo <= hi:
            size = (lo + hi) // 2
            font = ImageFont.truetype(str(self.font_path), size, layout_engine=ImageFont.Layout.RAQM)
            lines = _wrap_words(draw, text, font, width)
            line_height = max(1, int(size * 1.25))
            fits = bool(lines) and line_height * len(lines) <= height
            if fits:
                best = (lines, font)
                lo = size + 1
            else:
                hi = size - 1
        if best is None:
            raise EngineApiError("render_overflow", "Arabic translation does not fit the safe text region.", 409)
        return best


def _wrap_words(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = current + " " + word
        bbox = draw.textbbox((0, 0), candidate, font=font, direction="rtl", language="ar")
        if bbox[2] - bbox[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font, direction="rtl", language="ar")
        if bbox[2] - bbox[0] > max_width:
            return []
    return lines


def _bounds(block: EngineTextBlock) -> tuple[int, int, int, int]:
    xs = [p[0] for p in block.polygon]
    ys = [p[1] for p in block.polygon]
    return min(xs), min(ys), max(xs), max(ys)
