from __future__ import annotations

from collections.abc import Sequence

from PIL import Image, ImageDraw, ImageFilter, ImageChops

from ..errors import EngineApiError
from .contracts import EngineTextBlock

PROTECTED_MASK_REVISION = "protected-mask-source-composite-guard-v1"


def build_protected_mask(size: tuple[int, int], blocks: Sequence[EngineTextBlock], *, guard_pixels: int = 3) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    for block in blocks:
        if block.protected_from_editing:
            draw.polygon(block.polygon, fill=255)
    if guard_pixels > 0 and mask.getbbox() is not None:
        kernel = guard_pixels * 2 + 1
        mask = mask.filter(ImageFilter.MaxFilter(kernel))
    return mask


def build_erase_mask(size: tuple[int, int], blocks: Sequence[EngineTextBlock], protected_mask: Image.Image) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    for block in blocks:
        if block.processing_action == "translate-replace" and block.target_text:
            draw.polygon(block.polygon, fill=255)
    overlap = ImageChops.multiply(mask, protected_mask)
    if overlap.getbbox() is not None:
        raise EngineApiError("protected_region_conflict", "A destructive erase mask overlaps protected SFX/uncertain pixels.", 409)
    return mask


def ensure_render_regions_do_not_overlap_protected(blocks: Sequence[EngineTextBlock], protected_mask: Image.Image) -> None:
    for block in blocks:
        if block.processing_action != "translate-replace" or not block.target_text:
            continue
        region = Image.new("L", protected_mask.size, 0)
        ImageDraw.Draw(region).polygon(block.polygon, fill=255)
        if ImageChops.multiply(region, protected_mask).getbbox() is not None:
            raise EngineApiError("protected_region_conflict", "Arabic typesetting would overlap protected SFX/uncertain pixels.", 409)
