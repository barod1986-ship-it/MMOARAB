from __future__ import annotations

from collections.abc import Sequence

from ..errors import EngineApiError
from .contracts import EngineTextBlock

MAX_MANIFEST_BLOCKS = 512
MAX_MANIFEST_TEXT = 8192
MAX_MANIFEST_JSON_BYTES = 512 * 1024


def build_manifest(*, job_id: str, profile_fingerprint: str, blocks: Sequence[EngineTextBlock]) -> dict[str, object]:
    if len(blocks) > MAX_MANIFEST_BLOCKS:
        raise EngineApiError("invalid_result", "Result manifest contains too many text blocks.", 500)
    payload_blocks: list[dict[str, object]] = []
    for block in blocks:
        item: dict[str, object] = {
            "blockId": block.block_id,
            "blockKind": block.block_kind,
            "processingAction": block.processing_action,
            "sourceText": block.source_text[:MAX_MANIFEST_TEXT],
            "confidence": round(float(block.source_confidence), 6),
            "polygon": [[int(x), int(y)] for x, y in block.polygon],
            "readingOrder": block.reading_order,
            "protectedFromEditing": block.protected_from_editing,
            "styleHint": {"align": block.style_hints.align},
        }
        if block.processing_action == "translate-replace" and block.target_text is not None:
            item["translatedText"] = block.target_text[:MAX_MANIFEST_TEXT]
        payload_blocks.append(item)
    return {"schemaVersion": 1, "jobId": job_id[:128], "profileFingerprint": profile_fingerprint, "blocks": payload_blocks}


def validate_manifest(payload: dict[str, object], *, width: int, height: int) -> None:
    if payload.get("schemaVersion") != 1 or not isinstance(payload.get("jobId"), str):
        raise EngineApiError("invalid_result", "Result manifest header is invalid.", 500)
    fingerprint = payload.get("profileFingerprint")
    if not isinstance(fingerprint, str) or not fingerprint.startswith("sha256:") or len(fingerprint) != 71:
        raise EngineApiError("invalid_result", "Result manifest profile fingerprint is invalid.", 500)
    blocks = payload.get("blocks")
    if not isinstance(blocks, list) or len(blocks) > MAX_MANIFEST_BLOCKS:
        raise EngineApiError("invalid_result", "Result manifest block list is invalid.", 500)
    orders: set[int] = set()
    ids: set[str] = set()
    for item in blocks:
        if not isinstance(item, dict):
            raise EngineApiError("invalid_result", "Result manifest block is malformed.", 500)
        block_id = item.get("blockId")
        if not isinstance(block_id, str) or not block_id or len(block_id) > 64 or block_id in ids:
            raise EngineApiError("invalid_result", "Result manifest block ID is invalid.", 500)
        ids.add(block_id)
        kind = item.get("blockKind")
        action = item.get("processingAction")
        protected = item.get("protectedFromEditing")
        translated = item.get("translatedText")
        if kind in {"sfx", "other", "uncertain"}:
            if action != "preserve-original" or protected is not True or translated not in {None, ""}:
                raise EngineApiError("invalid_result", "Protected text block violates sfx-preserve-v1.", 500)
        elif kind in {"dialogue", "narration"}:
            if action != "translate-replace" or protected is not False or not isinstance(translated, str) or not translated.strip():
                raise EngineApiError("invalid_result", "Translatable text block is missing an accepted translation.", 500)
        else:
            raise EngineApiError("invalid_result", "Unknown block kind in result manifest.", 500)
        source = item.get("sourceText")
        if not isinstance(source, str) or len(source) > MAX_MANIFEST_TEXT or "\x00" in source:
            raise EngineApiError("invalid_result", "Result manifest source text is invalid.", 500)
        if isinstance(translated, str) and (len(translated) > MAX_MANIFEST_TEXT or "\x00" in translated):
            raise EngineApiError("invalid_result", "Result manifest translated text is invalid.", 500)
        confidence = item.get("confidence")
        if not isinstance(confidence, (float, int)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            raise EngineApiError("invalid_result", "Result manifest confidence is invalid.", 500)
        order = item.get("readingOrder")
        if not isinstance(order, int) or isinstance(order, bool) or order < 0 or order in orders:
            raise EngineApiError("invalid_result", "Result manifest reading order is invalid.", 500)
        orders.add(order)
        polygon = item.get("polygon")
        if not isinstance(polygon, list) or not 3 <= len(polygon) <= 16:
            raise EngineApiError("invalid_result", "Result manifest polygon is invalid.", 500)
        for point in polygon:
            if not isinstance(point, list) or len(point) != 2 or not all(isinstance(v, int) and not isinstance(v, bool) for v in point):
                raise EngineApiError("invalid_result", "Result manifest polygon point is invalid.", 500)
            x, y = point
            if not 0 <= x < width or not 0 <= y < height:
                raise EngineApiError("invalid_result", "Result manifest polygon leaves image bounds.", 500)
