from __future__ import annotations

import json
import re
from datetime import datetime
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from .common import is_sha256, require_dict, require_list, sha256_file
from .corpus_sources import CorpusSourceError, load_source_registry, source_registry_digest, validate_page_rights

CORPUS_SCHEMA_VERSION = 2
CORPUS_POLICY_REVISION = "rev10-production-corpus-v2"
ALLOWED_LANGUAGES = {"en", "ja", "ko", "zh-Hans", "zh-Hant"}
ALLOWED_KINDS = {"dialogue", "narration", "sfx", "other", "uncertain"}
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "AVIF"}
MAX_CORPUS_PAGES = 1000
MAX_BLOCKS_PER_PAGE = 512
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
REQUIRED_COVERAGE_FEATURES = {
    "black-and-white",
    "color",
    "small-text",
    "complex-background",
    "sfx-near-artwork",
    "long-webtoon-slice",
    "arabic-target-rendering",
}
LANGUAGE_SPECIFIC_FEATURES = {
    "ja": {"vertical-japanese", "furigana"},
    "en": {"english-uppercase-or-italic-or-outline"},
}


class CorpusError(ValueError):
    pass


def _fail(message: str) -> None:
    raise CorpusError(message)


def load_corpus(path: Path, *, verify_files: bool = True) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CorpusError(f"Cannot read corpus manifest: {exc}") from exc
    manifest = require_dict(raw, label="corpus")
    validate_corpus(manifest, base_dir=path.parent, verify_files=verify_files)
    return manifest


def validate_corpus(manifest: dict[str, Any], *, base_dir: Path, verify_files: bool = True) -> dict[str, Any]:
    if manifest.get("schemaVersion") != CORPUS_SCHEMA_VERSION:
        _fail("Unsupported corpus schemaVersion")
    if manifest.get("policyRevision") != CORPUS_POLICY_REVISION:
        _fail("Corpus policyRevision mismatch")
    registry = load_source_registry()
    if manifest.get("sourceRegistryRevision") != registry.get("registryRevision"):
        _fail("Corpus sourceRegistryRevision mismatch")
    if manifest.get("sourceRegistrySha256") != source_registry_digest(registry):
        _fail("Corpus sourceRegistrySha256 mismatch")
    corpus_id = manifest.get("corpusId")
    if not isinstance(corpus_id, str) or not corpus_id.strip():
        _fail("corpusId is required")
    pages = require_list(manifest.get("pages"), label="pages")
    if not pages:
        _fail("Corpus must contain at least one page")
    if len(pages) > MAX_CORPUS_PAGES:
        _fail(f"Corpus exceeds {MAX_CORPUS_PAGES} pages")

    seen: set[str] = set()
    image_hashes: set[str] = set()
    language_counts: Counter[str] = Counter()
    features: set[str] = set()
    language_features: dict[str, set[str]] = {language: set() for language in ALLOWED_LANGUAGES}
    authorized = 0
    ground_truth_sfx = 0
    ground_truth_sfx_by_language: Counter[str] = Counter()
    ground_truth_sfx_blocks: list[dict[str, str]] = []
    ground_truth_uncertain_blocks: list[dict[str, str]] = []
    clean_reference_pages = 0
    source_counts: Counter[str] = Counter()
    real_domain_language_counts: Counter[str] = Counter()
    supplemental_pages = 0
    rights_review_digests: set[str] = set()

    for index, item in enumerate(pages):
        page = require_dict(item, label=f"pages[{index}]")
        page_id = page.get("pageId")
        if not isinstance(page_id, str) or not page_id or len(page_id) > 128 or page_id in seen:
            _fail(f"pages[{index}].pageId must be unique and non-empty")
        seen.add(page_id)
        language = page.get("language")
        if language not in ALLOWED_LANGUAGES:
            _fail(f"{page_id}: unsupported language")
        language_counts[str(language)] += 1
        page_features = page.get("features")
        if not isinstance(page_features, list) or len(page_features) > 64 or any(not isinstance(v, str) or not v or len(v) > 80 for v in page_features):
            _fail(f"{page_id}: features must be a bounded non-empty string array")
        features.update(page_features)
        language_features[str(language)].update(page_features)

        rights = require_dict(page.get("rights"), label=f"{page_id}.rights")
        if rights.get("reviewed") is not True:
            _fail(f"{page_id}: rights.reviewed must be true")
        if rights.get("benchmarkUseAuthorized") is not True:
            _fail(f"{page_id}: benchmark use is not authorized")
        basis = rights.get("basis")
        source = rights.get("source")
        reviewer = rights.get("reviewedBy")
        reviewed_at = rights.get("reviewedAtUtc")
        evidence_ref = rights.get("evidenceRef")
        record_id = rights.get("reviewRecordId")
        if not isinstance(basis, str) or not basis.strip() or len(basis) > 512 or not isinstance(source, str) or not source.strip() or len(source) > 2048:
            _fail(f"{page_id}: rights basis/source are required")
        if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 256:
            _fail(f"{page_id}: rights.reviewedBy is required")
        if not isinstance(record_id, str) or not record_id.strip() or len(record_id) > 256:
            _fail(f"{page_id}: rights.reviewRecordId is required")
        if not isinstance(evidence_ref, str) or not evidence_ref.strip() or len(evidence_ref) > 2048:
            _fail(f"{page_id}: rights.evidenceRef is required")
        if not isinstance(reviewed_at, str) or not UTC_RE.fullmatch(reviewed_at):
            _fail(f"{page_id}: rights.reviewedAtUtc must be an ISO-8601 UTC timestamp ending in Z")
        try:
            datetime.fromisoformat(reviewed_at[:-1] + "+00:00")
        except ValueError:
            _fail(f"{page_id}: rights.reviewedAtUtc is invalid")
        try:
            rights_meta = validate_page_rights(page_id=str(page_id), language=str(language), rights=rights, base_dir=base_dir, registry=registry, verify_files=verify_files)
        except CorpusSourceError as exc:
            _fail(str(exc))
        source_counts[str(rights_meta["sourceId"])] += 1
        rights_review_digests.add(str(rights_meta["reviewRecordSha256"]))
        if rights_meta["realDomain"]:
            real_domain_language_counts[str(language)] += 1
        if rights_meta["supplementalOnly"]:
            supplemental_pages += 1
        authorized += 1

        image_rel = page.get("imagePath")
        annotation_rel = page.get("annotationPath")
        if not isinstance(image_rel, str) or not image_rel or not isinstance(annotation_rel, str) or not annotation_rel:
            _fail(f"{page_id}: imagePath and annotationPath are required")
        image_sha = page.get("imageSha256")
        annotation_sha = page.get("annotationSha256")
        if not is_sha256(image_sha) or not is_sha256(annotation_sha):
            _fail(f"{page_id}: imageSha256 and annotationSha256 must be sha256 digests")
        if image_sha in image_hashes:
            _fail(f"{page_id}: duplicate imageSha256 is not allowed in the production corpus")
        image_hashes.add(str(image_sha))

        if verify_files:
            image_path = _safe_corpus_path(base_dir, image_rel, page_id=page_id, label="imagePath")
            annotation_path = _safe_corpus_path(base_dir, annotation_rel, page_id=page_id, label="annotationPath")
            if not image_path.is_file() or not annotation_path.is_file():
                _fail(f"{page_id}: corpus file is missing")
            if sha256_file(image_path) != image_sha or sha256_file(annotation_path) != annotation_sha:
                _fail(f"{page_id}: corpus file digest mismatch")
            image_size = _verify_image(image_path, page_id=page_id)
            annotation = _validate_annotation(annotation_path, page_id=page_id, image_size=image_size)
            page_has_sfx = False
            for block in annotation["blocks"]:
                if block.get("kind") == "sfx":
                    page_has_sfx = True
                    ground_truth_sfx_blocks.append({"pageId": str(page_id), "blockId": str(block["blockId"]), "language": str(language)})
                elif block.get("kind") == "uncertain":
                    ground_truth_uncertain_blocks.append({"pageId": str(page_id), "blockId": str(block["blockId"]), "language": str(language)})
            if page_has_sfx:
                ground_truth_sfx += 1
                ground_truth_sfx_by_language[str(language)] += 1
        else:
            # Explicit manifest declaration is still required when validating structure only.
            if page.get("hasGroundTruthSfx") is True:
                ground_truth_sfx += 1
                ground_truth_sfx_by_language[str(language)] += 1

        clean_ref = page.get("cleanReferencePath")
        clean_sha = page.get("cleanReferenceSha256")
        if clean_ref is not None or clean_sha is not None:
            if not isinstance(clean_ref, str) or not is_sha256(clean_sha):
                _fail(f"{page_id}: clean-reference path/hash must appear together")
            clean_reference_pages += 1
            if verify_files:
                clean_path = _safe_corpus_path(base_dir, clean_ref, page_id=page_id, label="cleanReferencePath")
                if not clean_path.is_file() or sha256_file(clean_path) != clean_sha:
                    _fail(f"{page_id}: clean-reference digest mismatch")
                clean_size = _verify_image(clean_path, page_id=page_id)
                if clean_size != image_size:
                    _fail(f"{page_id}: clean-reference dimensions must match source image")

    missing_coverage = REQUIRED_COVERAGE_FEATURES - features
    return {
        "pageCount": len(pages),
        "languageCounts": dict(sorted(language_counts.items())),
        "authorizedPages": authorized,
        "uniqueImageCount": len(image_hashes),
        "coverageFeatures": sorted(features),
        "languageFeatures": {lang: sorted(values) for lang, values in sorted(language_features.items()) if language_counts.get(lang, 0)},
        "missingCoverageFeatures": sorted(missing_coverage),
        "groundTruthSfxPages": ground_truth_sfx,
        "groundTruthSfxPagesByLanguage": dict(sorted(ground_truth_sfx_by_language.items())),
        "groundTruthSfxBlocks": ground_truth_sfx_blocks,
        "groundTruthUncertainBlocks": ground_truth_uncertain_blocks,
        "cleanReferencePages": clean_reference_pages,
        "sourceCounts": dict(sorted(source_counts.items())),
        "realDomainLanguageCounts": dict(sorted(real_domain_language_counts.items())),
        "supplementalPages": supplemental_pages,
        "rightsReviewRecordCount": len(rights_review_digests),
        "sourceRegistryRevision": registry["registryRevision"],
        "sourceRegistrySha256": source_registry_digest(registry),
    }


def _validate_annotation(path: Path, *, page_id: str, image_size: tuple[int, int]) -> dict[str, Any]:
    try:
        annotation = require_dict(json.loads(path.read_text(encoding="utf-8")), label=f"{page_id}.annotation")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise CorpusError(f"{page_id}: invalid annotation: {exc}") from exc
    if annotation.get("schemaVersion") != 1:
        _fail(f"{page_id}: annotation schemaVersion must be 1")
    blocks = require_list(annotation.get("blocks"), label=f"{page_id}.annotation.blocks")
    if len(blocks) > MAX_BLOCKS_PER_PAGE:
        _fail(f"{page_id}: annotation exceeds {MAX_BLOCKS_PER_PAGE} blocks")
    block_ids: set[str] = set()
    for idx, raw in enumerate(blocks):
        block = require_dict(raw, label=f"{page_id}.blocks[{idx}]")
        block_id = block.get("blockId")
        kind = block.get("kind")
        polygon = block.get("polygon")
        text = block.get("text")
        if not isinstance(block_id, str) or not block_id or block_id in block_ids:
            _fail(f"{page_id}: annotation block IDs must be unique")
        block_ids.add(block_id)
        if kind not in ALLOWED_KINDS:
            _fail(f"{page_id}/{block_id}: invalid kind")
        if not isinstance(text, str) or len(text) > 4096:
            _fail(f"{page_id}/{block_id}: text must be a bounded string")
        if not isinstance(polygon, list) or not 3 <= len(polygon) <= 16:
            _fail(f"{page_id}/{block_id}: polygon must contain 3..16 points")
        width, height = image_size
        for point in polygon:
            if not isinstance(point, list) or len(point) != 2 or any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in point):
                _fail(f"{page_id}/{block_id}: polygon coordinates must be non-negative integers")
            if point[0] >= width or point[1] >= height:
                _fail(f"{page_id}/{block_id}: polygon leaves image bounds")
        order = block.get("readingOrder")
        if order is not None and (isinstance(order, bool) or not isinstance(order, int) or order < 0):
            _fail(f"{page_id}/{block_id}: readingOrder must be a non-negative integer")
    return annotation


def production_corpus_gate(summary: dict[str, Any]) -> tuple[bool, list[str]]:
    counts = summary.get("languageCounts", {})
    real_counts = summary.get("realDomainLanguageCounts", {})
    reasons: list[str] = []
    # Synthetic/self-authored pages may exercise edge cases but cannot satisfy
    # production-domain minimums. Every required language count must be backed
    # by real manga/manhwa/webtoon pages with reviewed rights evidence.
    if int(real_counts.get("en", 0)) < 60:
        reasons.append("need at least 60 real-domain English primary pages with rights-chain evidence")
    for language, label in (("ja", "Japanese"), ("ko", "Korean")):
        if int(real_counts.get(language, 0)) < 10:
            reasons.append(f"need at least 10 real-domain {label} fallback pages with rights-chain evidence")
    if int(real_counts.get("zh-Hans", 0)) + int(real_counts.get("zh-Hant", 0)) < 10:
        reasons.append("need at least 10 real-domain Chinese fallback pages with rights-chain evidence")
    if int(counts.get("en", 0)) < 60:
        reasons.append("need at least 60 English primary pages")
    for language, label in (("ja", "Japanese"), ("ko", "Korean")):
        if int(counts.get(language, 0)) < 10:
            reasons.append(f"need at least 10 {label} fallback pages")
    if int(counts.get("zh-Hans", 0)) + int(counts.get("zh-Hant", 0)) < 10:
        reasons.append("need at least 10 Chinese fallback pages")
    if int(counts.get("zh-Hans", 0)) == 0 or int(counts.get("zh-Hant", 0)) == 0:
        reasons.append("Chinese fallback corpus must represent both Simplified and Traditional scripts")
    missing = set(summary.get("missingCoverageFeatures", []))
    if missing:
        reasons.append("missing required visual coverage: " + ", ".join(sorted(missing)))
    language_features = summary.get("languageFeatures", {})
    for language, required in LANGUAGE_SPECIFIC_FEATURES.items():
        available = set(language_features.get(language, [])) if isinstance(language_features, dict) else set()
        if int(counts.get(language, 0)) and not required.issubset(available):
            reasons.append(f"missing {language}-specific coverage: " + ", ".join(sorted(required - available)))
    if int(summary.get("groundTruthSfxPages", 0)) < 10:
        reasons.append("need at least 10 pages with independent ground-truth SFX annotations")
    sfx_by_language = summary.get("groundTruthSfxPagesByLanguage", {})
    required_sfx = {"en": 5, "ja": 1, "ko": 1, "zh-Hans": 1, "zh-Hant": 1}
    if isinstance(sfx_by_language, dict):
        for language, minimum in required_sfx.items():
            if int(counts.get(language, 0)) and int(sfx_by_language.get(language, 0)) < minimum:
                reasons.append(f"need at least {minimum} ground-truth SFX page(s) for {language}")
    if int(summary.get("cleanReferencePages", 0)) < 5:
        reasons.append("need at least 5 clean-reference pages for quantitative inpainting checks")
    return not reasons, reasons


def _safe_corpus_path(base_dir: Path, relative: str, *, page_id: str, label: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        _fail(f"{page_id}: {label} must stay inside the corpus directory")
    base = base_dir.resolve()
    unresolved = base / candidate
    cursor = base
    for part in candidate.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            _fail(f"{page_id}: {label} may not traverse symlinks")
    resolved = unresolved.resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        _fail(f"{page_id}: {label} escapes the corpus directory")
    return resolved


def _verify_image(path: Path, *, page_id: str) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            if image.format not in ALLOWED_IMAGE_FORMATS:
                _fail(f"{page_id}: benchmark image format must match an Engine V1 source format")
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > 120_000_000:
                _fail(f"{page_id}: benchmark image dimensions exceed the Engine V1 guard")
            if getattr(image, "n_frames", 1) != 1:
                _fail(f"{page_id}: animated benchmark images are unsupported")
            image.verify()
            return width, height
    except CorpusError:
        raise
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        raise CorpusError(f"{page_id}: benchmark image cannot be verified: {exc}") from exc
