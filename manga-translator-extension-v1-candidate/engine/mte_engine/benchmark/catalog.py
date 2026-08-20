from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from .common import is_sha256, require_dict, require_list, sha256_path

CATALOG_SCHEMA_VERSION = 1
ALLOWED_LICENSE_STATUS = {"approved", "pending", "blocked"}
ALLOWED_REDISTRIBUTION = {"approved", "local-only", "pending", "blocked"}
ALLOWED_BENCHMARK_USE = {"approved", "pending", "blocked"}


class CatalogError(ValueError):
    pass


def load_catalog(path: Path, *, artifacts_dir: Path | None = None, require_local_hashes: bool = False) -> dict[str, Any]:
    try:
        catalog = require_dict(json.loads(path.read_text(encoding="utf-8")), label="model catalog")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise CatalogError(f"Cannot read model catalog: {exc}") from exc
    validate_catalog(catalog, artifacts_dir=artifacts_dir, require_local_hashes=require_local_hashes)
    return catalog


def validate_catalog(catalog: dict[str, Any], *, artifacts_dir: Path | None = None, require_local_hashes: bool = False) -> None:
    if catalog.get("schemaVersion") != CATALOG_SCHEMA_VERSION:
        raise CatalogError("Unsupported model catalog schemaVersion")
    if not isinstance(catalog.get("catalogRevision"), str) or not catalog["catalogRevision"]:
        raise CatalogError("catalogRevision is required")
    items = require_list(catalog.get("artifacts"), label="artifacts")
    seen: set[str] = set()
    for idx, raw in enumerate(items):
        item = require_dict(raw, label=f"artifacts[{idx}]")
        artifact_id = item.get("artifactId")
        if not isinstance(artifact_id, str) or not artifact_id or artifact_id in seen:
            raise CatalogError("artifactId must be unique and non-empty")
        seen.add(artifact_id)
        for key in ("kind", "upstreamProject", "upstreamRevision", "sourceUrl", "expectedFilename", "codeLicense"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise CatalogError(f"{artifact_id}: {key} is required")
        parsed = urlparse(str(item["sourceUrl"]))
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise CatalogError(f"{artifact_id}: sourceUrl must be a credential-free HTTPS URL")
        _validate_expected_filename(str(item["expectedFilename"]), artifact_id=artifact_id)
        if item.get("benchmarkUseStatus") not in ALLOWED_BENCHMARK_USE:
            raise CatalogError(f"{artifact_id}: invalid benchmarkUseStatus")
        if item.get("artifactLicenseStatus") not in ALLOWED_LICENSE_STATUS:
            raise CatalogError(f"{artifact_id}: invalid artifactLicenseStatus")
        if item.get("redistributionStatus") not in ALLOWED_REDISTRIBUTION:
            raise CatalogError(f"{artifact_id}: invalid redistributionStatus")
        sha = item.get("sha256")
        if sha is not None and not is_sha256(sha):
            raise CatalogError(f"{artifact_id}: malformed sha256")
        if require_local_hashes and not is_sha256(sha):
            raise CatalogError(f"{artifact_id}: local SHA-256 pin is required")
        if artifacts_dir is not None and is_sha256(sha):
            path = resolve_artifact_path(artifacts_dir, str(item["expectedFilename"]), artifact_id=artifact_id)
            if not path.exists():
                raise CatalogError(f"{artifact_id}: pinned local artifact is missing")
            if sha256_path(path) != sha:
                raise CatalogError(f"{artifact_id}: local artifact digest mismatch")


def artifact_by_id(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["artifactId"]): item for item in catalog["artifacts"]}


def selected_artifacts_release_ready(catalog: dict[str, Any], selected_ids: list[str], *, artifacts_dir: Path | None = None) -> tuple[bool, list[str]]:
    by_id = artifact_by_id(catalog)
    reasons: list[str] = []
    if not selected_ids:
        reasons.append("no selected model artifacts")
    for artifact_id in selected_ids:
        item = by_id.get(artifact_id)
        if item is None:
            reasons.append(f"selected artifact is absent from catalog: {artifact_id}")
            continue
        if not is_sha256(item.get("sha256")):
            reasons.append(f"selected artifact has no SHA-256 pin: {artifact_id}")
        if item.get("benchmarkUseStatus") != "approved":
            reasons.append(f"benchmark use is not approved for selected artifact: {artifact_id}")
        if item.get("artifactLicenseStatus") != "approved":
            reasons.append(f"artifact license is not approved: {artifact_id}")
        if item.get("redistributionStatus") not in {"approved", "local-only"}:
            reasons.append(f"artifact redistribution/provisioning status is unresolved: {artifact_id}")
        if artifacts_dir is not None and is_sha256(item.get("sha256")):
            path = resolve_artifact_path(artifacts_dir, str(item["expectedFilename"]), artifact_id=artifact_id)
            if not path.exists():
                reasons.append(f"selected local artifact is missing: {artifact_id}")
            else:
                try:
                    if sha256_path(path) != item["sha256"]:
                        reasons.append(f"selected local artifact digest mismatch: {artifact_id}")
                except (OSError, ValueError):
                    reasons.append(f"selected local artifact cannot be safely hashed: {artifact_id}")
    return not reasons, reasons


def _validate_expected_filename(value: str, *, artifact_id: str) -> None:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or value in {"", "."}:
        raise CatalogError(f"{artifact_id}: expectedFilename must be a safe relative path")


def resolve_artifact_path(base_dir: Path, relative: str, *, artifact_id: str) -> Path:
    _validate_expected_filename(relative, artifact_id=artifact_id)
    base = base_dir.resolve()
    candidate = Path(relative)
    cursor = base
    for part in candidate.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise CatalogError(f"{artifact_id}: symlink model artifacts are refused")
    unresolved = base / candidate
    resolved = unresolved.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise CatalogError(f"{artifact_id}: artifact path escapes the model directory") from exc
    return resolved
