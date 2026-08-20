from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

from .common import canonical_json, is_sha256, require_dict, require_list, sha256_bytes, sha256_path

SOURCE_REGISTRY_SCHEMA_VERSION = 1
SOURCE_REGISTRY_REVISION = "production-corpus-sources-2026-08-19-v1"
RIGHTS_REVIEW_SCHEMA_VERSION = 1
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


class CorpusSourceError(ValueError):
    pass


def _default_registry_path() -> Path:
    return Path(__file__).resolve().parents[2] / "benchmark" / "corpus" / "corpus-source-registry-v1.json"


def source_registry_digest(registry: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json(registry))


def load_source_registry(path: Path | None = None) -> dict[str, Any]:
    target = (path or _default_registry_path()).resolve()
    try:
        registry = require_dict(json.loads(target.read_text(encoding="utf-8")), label="corpus source registry")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise CorpusSourceError(f"cannot read corpus source registry: {exc}") from exc
    validate_source_registry(registry)
    return registry


def validate_source_registry(registry: dict[str, Any]) -> None:
    if registry.get("schemaVersion") != SOURCE_REGISTRY_SCHEMA_VERSION:
        raise CorpusSourceError("unsupported corpus source registry schemaVersion")
    if registry.get("registryRevision") != SOURCE_REGISTRY_REVISION:
        raise CorpusSourceError("corpus source registry revision mismatch")
    sources = require_dict(registry.get("sources"), label="corpus source registry sources")
    if not sources:
        raise CorpusSourceError("corpus source registry is empty")
    for source_id, raw in sources.items():
        if not isinstance(source_id, str) or not source_id or len(source_id) > 128:
            raise CorpusSourceError("corpus source registry has an invalid sourceId")
        item = require_dict(raw, label=f"source registry {source_id}")
        if item.get("sourceKind") not in {"operator-rights", "licensed-dataset", "public-dataset", "synthetic"}:
            raise CorpusSourceError(f"{source_id}: unsupported sourceKind")
        if not isinstance(item.get("sourceRevision"), str) or not item["sourceRevision"].strip():
            raise CorpusSourceError(f"{source_id}: sourceRevision is required")
        languages = require_list(item.get("languages"), label=f"{source_id}.languages")
        if not languages or any(v not in {"en", "ja", "ko", "zh-Hans", "zh-Hant"} for v in languages):
            raise CorpusSourceError(f"{source_id}: invalid languages")
        if not isinstance(item.get("commercialQualificationAllowed"), bool) or not isinstance(item.get("realDomain"), bool):
            raise CorpusSourceError(f"{source_id}: qualification booleans are required")
        if not isinstance(item.get("sourceWideEvidenceAllowed"), bool) or not isinstance(item.get("redistributionDefault"), bool):
            raise CorpusSourceError(f"{source_id}: evidence/redistribution booleans are required")
        terms = item.get("termsUrl")
        if terms is not None:
            _https_no_credentials(terms, label=f"{source_id}.termsUrl")


def source_entry(registry: dict[str, Any], source_id: str) -> dict[str, Any]:
    sources = require_dict(registry.get("sources"), label="corpus source registry sources")
    item = sources.get(source_id)
    if not isinstance(item, dict):
        raise CorpusSourceError(f"unknown corpus sourceId: {source_id}")
    return item


def validate_page_rights(
    *,
    page_id: str,
    language: str,
    rights: dict[str, Any],
    base_dir: Path,
    registry: dict[str, Any],
    verify_files: bool,
) -> dict[str, Any]:
    source_id = rights.get("sourceId")
    if not isinstance(source_id, str) or not source_id:
        raise CorpusSourceError(f"{page_id}: rights.sourceId is required")
    source = source_entry(registry, source_id)
    if language not in source["languages"]:
        raise CorpusSourceError(f"{page_id}: source {source_id} does not cover language {language}")
    if source.get("commercialQualificationAllowed") is not True:
        raise CorpusSourceError(f"{page_id}: source {source_id} is not eligible for production/commercial V1 qualification")
    if source.get("v1Qualification") == "supplemental-only":
        supplemental = True
    else:
        supplemental = False

    source_revision = rights.get("sourceRevision")
    if not isinstance(source_revision, str) or not source_revision:
        raise CorpusSourceError(f"{page_id}: rights.sourceRevision is required")
    expected_revision = str(source["sourceRevision"])
    if expected_revision != "per-review-record" and source_revision != expected_revision:
        raise CorpusSourceError(f"{page_id}: rights.sourceRevision does not match source registry")

    review_path_raw = rights.get("reviewRecordPath")
    review_sha = rights.get("reviewRecordSha256")
    if not isinstance(review_path_raw, str) or not review_path_raw or not is_sha256(review_sha):
        raise CorpusSourceError(f"{page_id}: rights review path/hash are required")
    review_path = _contained(base_dir, review_path_raw, label=f"{page_id}.rights.reviewRecordPath")
    if verify_files:
        if not review_path.is_file():
            raise CorpusSourceError(f"{page_id}: rights review file is missing")
        if sha256_path(review_path) != review_sha:
            raise CorpusSourceError(f"{page_id}: rights review digest mismatch")
        review = _load_rights_review(review_path)
        _validate_review_for_page(page_id=page_id, source_id=source_id, source=source, source_revision=source_revision, rights=rights, review=review)
    else:
        review = None

    return {
        "sourceId": source_id,
        "sourceKind": source["sourceKind"],
        "realDomain": bool(source["realDomain"]),
        "supplementalOnly": supplemental,
        "reviewRecordId": rights.get("reviewRecordId"),
        "reviewRecordSha256": review_sha,
    }


def _load_rights_review(path: Path) -> dict[str, Any]:
    try:
        return require_dict(json.loads(path.read_text(encoding="utf-8")), label="corpus rights review")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise CorpusSourceError(f"cannot read corpus rights review: {exc}") from exc


def _validate_review_for_page(*, page_id: str, source_id: str, source: dict[str, Any], source_revision: str, rights: dict[str, Any], review: dict[str, Any]) -> None:
    if review.get("schemaVersion") != RIGHTS_REVIEW_SCHEMA_VERSION:
        raise CorpusSourceError(f"{page_id}: unsupported rights review schemaVersion")
    if review.get("sourceId") != source_id:
        raise CorpusSourceError(f"{page_id}: rights review sourceId mismatch")
    review_revision = review.get("sourceRevision")
    if not isinstance(review_revision, str) or not review_revision:
        raise CorpusSourceError(f"{page_id}: rights review sourceRevision is required")
    if source["sourceRevision"] == "per-review-record":
        if review_revision != source_revision:
            raise CorpusSourceError(f"{page_id}: rights review sourceRevision mismatch")
    elif review_revision != source["sourceRevision"]:
        raise CorpusSourceError(f"{page_id}: rights review sourceRevision does not match registry")
    if review.get("reviewRecordId") != rights.get("reviewRecordId"):
        raise CorpusSourceError(f"{page_id}: rights review record ID mismatch")
    for key in ("reviewer", "reviewedAtUtc"):
        if not isinstance(review.get(key), str) or not review[key].strip():
            raise CorpusSourceError(f"{page_id}: rights review requires {key}")
    if not UTC_RE.fullmatch(str(review["reviewedAtUtc"])):
        raise CorpusSourceError(f"{page_id}: rights review timestamp must be UTC")
    if review.get("reviewer") != rights.get("reviewedBy") or review.get("reviewedAtUtc") != rights.get("reviewedAtUtc"):
        raise CorpusSourceError(f"{page_id}: rights review attribution does not match manifest")
    if review.get("benchmarkUseAuthorized") is not True or review.get("commercialV1QualificationAuthorized") is not True:
        raise CorpusSourceError(f"{page_id}: rights review does not authorize production V1 benchmark use")
    if bool(review.get("redistributionAuthorized")) != bool(rights.get("redistributionAuthorized")):
        raise CorpusSourceError(f"{page_id}: redistribution decision differs from rights review")
    if rights.get("redistributionAuthorized") is True and source.get("redistributionDefault") is not True:
        raise CorpusSourceError(f"{page_id}: redistribution exceeds source registry policy")
    coverage_mode = review.get("coverageMode")
    page_ids = require_list(review.get("pageIds"), label=f"{page_id}.rightsReview.pageIds")
    if coverage_mode == "page-list":
        if page_id not in page_ids:
            raise CorpusSourceError(f"{page_id}: rights review does not enumerate this page")
    elif coverage_mode == "source-wide":
        if source.get("sourceWideEvidenceAllowed") is not True:
            raise CorpusSourceError(f"{page_id}: source-wide rights evidence is not permitted for {source_id}")
    else:
        raise CorpusSourceError(f"{page_id}: rights review coverageMode is invalid")
    evidence = require_list(review.get("evidence"), label=f"{page_id}.rightsReview.evidence")
    if not evidence:
        raise CorpusSourceError(f"{page_id}: rights review evidence must not be empty")
    for index, raw in enumerate(evidence):
        item = require_dict(raw, label=f"{page_id}.rightsReview.evidence[{index}]")
        if not isinstance(item.get("kind"), str) or not item["kind"].strip():
            raise CorpusSourceError(f"{page_id}: rights review evidence kind is required")
        ref = item.get("ref")
        url = item.get("url")
        if (not isinstance(ref, str) or not ref.strip()) and url is None:
            raise CorpusSourceError(f"{page_id}: rights review evidence needs ref or url")
        if url is not None:
            _https_no_credentials(url, label=f"{page_id}.rightsReview.evidence[{index}].url")


def _contained(root: Path, relative: str, *, label: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise CorpusSourceError(f"{label} must stay inside the corpus directory")
    base = root.resolve()
    cursor = base
    for part in pure.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise CorpusSourceError(f"{label} may not traverse symlinks")
    resolved = cursor.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise CorpusSourceError(f"{label} escapes the corpus directory") from exc
    return resolved


def _https_no_credentials(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CorpusSourceError(f"{label} must be HTTPS")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise CorpusSourceError(f"{label} must be credential-free HTTPS")
    return value
