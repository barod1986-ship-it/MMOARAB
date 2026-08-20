from __future__ import annotations

import json
import re
import socket
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from ..errors import EngineApiError
from .contracts import TranslatedBlock, TranslationInputBlock


TRANSLATION_SCHEMA_REVISION = "page-batch-id-mapped-translation-v2"
OPENAI_TRANSLATOR_ADAPTER = "openai-responses-structured-v1"
OPENAI_PRIVACY_MODE = "external-ocr-text-only-v1"
_OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
_DATED_MODEL_RE = re.compile(r"^gpt-[a-z0-9.-]+-\d{4}-\d{2}-\d{2}$")
_MAX_BLOCKS = 512
_MAX_SOURCE_CHARS = 4096
_MAX_TRANSLATED_CHARS = 8192
_MAX_REQUEST_CHARS = 256_000


class ReferenceTranslator:
    adapter_id = "reference-arabic-translator-v1"

    def __init__(self, translations: Mapping[str, str] | None = None) -> None:
        self._translations = dict(translations or {})

    def translate_page(self, *, source_language: str, target_language: str, blocks: Sequence[TranslationInputBlock]) -> Sequence[TranslatedBlock]:
        if target_language != "ar":
            raise EngineApiError("translation_failed", "Reference translator only supports the V1 Arabic target.", 400)
        return [TranslatedBlock(block.block_id, self._translations.get(block.source, f"ترجمة: {block.source}")) for block in blocks]


class OpenAIResponsesTranslator:
    """Text-only page-batch translator with exact block-ID mapping.

    Only OCR text for blocks already approved by the SFX/role gate is sent. Images,
    polygons, page URLs, and visual context are never included in this adapter.
    """

    adapter_id = OPENAI_TRANSLATOR_ADAPTER

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        request_fn: Callable[[str, dict[str, str], bytes, float], tuple[int, bytes]] | None = None,
        timeout_seconds: float = 45.0,
    ) -> None:
        if not api_key.strip():
            raise EngineApiError("provider_misconfigured", "OpenAI API key is not configured.", 409)
        if not _DATED_MODEL_RE.fullmatch(model):
            raise EngineApiError("provider_misconfigured", "Production translation requires an immutable dated OpenAI model revision from the benchmark freeze.", 409)
        if not 1.0 <= timeout_seconds <= 120.0:
            raise ValueError("timeout_seconds must be within 1..120")
        self._api_key = api_key.strip()
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._request_fn = request_fn or _https_post

    def translate_page(self, *, source_language: str, target_language: str, blocks: Sequence[TranslationInputBlock]) -> Sequence[TranslatedBlock]:
        if target_language != "ar":
            raise EngineApiError("translation_failed", "Production V1 translator only supports Arabic output.", 400)
        if not blocks:
            return ()
        _validate_input_blocks(blocks)
        input_body = {
            "sourceLanguage": source_language,
            "targetLanguage": "ar",
            "blocks": [{"id": block.block_id, "text": block.source} for block in blocks],
        }
        compact_input = json.dumps(input_body, ensure_ascii=False, separators=(",", ":"))
        if len(compact_input) > _MAX_REQUEST_CHARS:
            raise EngineApiError("translation_failed", "Page translation request exceeds the V1 text bound.", 413)
        body = {
            "model": self.model,
            "store": False,
            "instructions": (
                "Translate the provided manga/manhwa dialogue and narration into natural Modern Standard Arabic. "
                "Preserve meaning, tone, names, numbers, and punctuation where appropriate. Do not add explanations. "
                "The input has already been filtered by a local role/SFX safety gate; return exactly one translation "
                "for each supplied id, with no extra ids and no omitted ids."
            ),
            "input": compact_input,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "manga_page_translation",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "translations": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {"id": {"type": "string"}, "text": {"type": "string"}},
                                    "required": ["id", "text"],
                                    "additionalProperties": False,
                                },
                            }
                        },
                        "required": ["translations"],
                        "additionalProperties": False,
                    },
                }
            },
        }
        payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            status, raw = self._request_fn(_OPENAI_RESPONSES_URL, headers, payload, self.timeout_seconds)
        except EngineApiError:
            raise
        except (OSError, TimeoutError, socket.timeout) as exc:
            raise EngineApiError("translation_provider_unavailable", f"Translation provider request failed: {exc}", 502, retryable=True) from exc
        if status == 429 or 500 <= status <= 599:
            raise EngineApiError("translation_provider_unavailable", f"Translation provider returned HTTP {status}.", 502, retryable=True)
        if status < 200 or status >= 300:
            raise EngineApiError("translation_failed", f"Translation provider returned HTTP {status}.", 502)
        try:
            response = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EngineApiError("translation_failed", "Translation provider returned invalid JSON.", 502) from exc
        if not isinstance(response, dict):
            raise EngineApiError("translation_failed", "Translation provider response is malformed.", 502)
        if response.get("status") == "incomplete":
            raise EngineApiError("translation_failed", "Translation provider returned an incomplete response.", 502, retryable=True)
        text = _extract_output_text(response)
        try:
            structured = json.loads(text)
        except json.JSONDecodeError as exc:
            raise EngineApiError("translation_failed", "Structured translation output is not valid JSON.", 502) from exc
        return _validate_translations(structured, blocks)


class UnconfiguredTranslator:
    adapter_id = "translator-unconfigured-v1"

    def translate_page(self, *, source_language: str, target_language: str, blocks: Sequence[TranslationInputBlock]) -> Sequence[TranslatedBlock]:
        raise EngineApiError("provider_misconfigured", "No trusted translation provider is configured for the production profile.", 409)


def production_translation_support(translation: object) -> tuple[bool, str | None, bool]:
    """Return (supported, reason, text_leaves_device)."""
    if not isinstance(translation, dict):
        return False, "translation freeze metadata is missing", False
    adapter = translation.get("adapterId")
    revision = translation.get("modelOrProviderRevision")
    privacy = translation.get("privacyMode")
    if adapter != OPENAI_TRANSLATOR_ADAPTER:
        return False, f"unsupported frozen translation adapter: {adapter!r}", False
    if not isinstance(revision, str) or not _DATED_MODEL_RE.fullmatch(revision):
        return False, "translation model/provider revision is not an immutable dated OpenAI model", True
    if privacy != OPENAI_PRIVACY_MODE:
        return False, f"unsupported translation privacy mode: {privacy!r}", True
    return True, None, True


def _validate_input_blocks(blocks: Sequence[TranslationInputBlock]) -> None:
    if len(blocks) > _MAX_BLOCKS:
        raise EngineApiError("translation_failed", "Too many translation blocks for one page.", 413)
    ids: set[str] = set()
    for block in blocks:
        if not block.block_id or len(block.block_id) > 64 or block.block_id in ids:
            raise EngineApiError("translation_failed", "Translation input block IDs must be unique bounded strings.", 500)
        ids.add(block.block_id)
        if not block.source.strip() or len(block.source) > _MAX_SOURCE_CHARS or "\x00" in block.source:
            raise EngineApiError("translation_failed", "Translation source text violates the V1 bounds.", 500)


def _extract_output_text(response: dict[str, Any]) -> str:
    output = response.get("output")
    if not isinstance(output, list):
        raise EngineApiError("translation_failed", "Translation provider response omitted output.", 502)
    pieces: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "refusal":
                raise EngineApiError("translation_failed", "Translation provider refused the page translation request.", 502)
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                pieces.append(part["text"])
    if len(pieces) != 1 or not pieces[0].strip():
        raise EngineApiError("translation_failed", "Translation provider must return exactly one structured output payload.", 502)
    return pieces[0]


def _validate_translations(value: object, blocks: Sequence[TranslationInputBlock]) -> tuple[TranslatedBlock, ...]:
    if not isinstance(value, dict) or set(value) != {"translations"} or not isinstance(value["translations"], list):
        raise EngineApiError("translation_failed", "Structured translation output does not match the required schema.", 502)
    expected = [block.block_id for block in blocks]
    seen: dict[str, str] = {}
    for item in value["translations"]:
        if not isinstance(item, dict) or set(item) != {"id", "text"}:
            raise EngineApiError("translation_failed", "Structured translation item is malformed.", 502)
        block_id = item.get("id")
        text = item.get("text")
        if not isinstance(block_id, str) or block_id not in expected or block_id in seen:
            raise EngineApiError("translation_failed", "Translation provider returned an unknown or duplicate block ID.", 502)
        if not isinstance(text, str) or not text.strip() or len(text) > _MAX_TRANSLATED_CHARS or "\x00" in text:
            raise EngineApiError("translation_failed", "Translation provider returned invalid translated text.", 502)
        seen[block_id] = text.strip()
    if set(seen) != set(expected):
        raise EngineApiError("translation_failed", "Translation provider omitted one or more requested block IDs.", 502)
    # Preserve local reading order even if the provider returns the JSON array reordered.
    return tuple(TranslatedBlock(block_id, seen[block_id]) for block_id in expected)


def _https_post(url: str, headers: dict[str, str], payload: bytes, timeout: float) -> tuple[int, bytes]:
    if url != _OPENAI_RESPONSES_URL:
        raise EngineApiError("provider_misconfigured", "V1 translation provider endpoint is not allowlisted.", 409)
    req = urlrequest.Request(url, data=payload, method="POST", headers=headers)
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:  # noqa: S310 - fixed HTTPS endpoint above
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise EngineApiError("translation_failed", "Translation provider response exceeds the V1 bound.", 502)
            return int(response.status), raw
    except urlerror.HTTPError as exc:
        raw = exc.read(64 * 1024)
        return int(exc.code), raw
