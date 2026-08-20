from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

from .common import canonical_json, is_sha256, require_dict, require_list, sha256_bytes, sha256_path
from .provenance import artifact_stats

SOURCE_REGISTRY_SCHEMA_VERSION = 3
LEGACY_SOURCE_REGISTRY_SCHEMA_VERSION = 2
ACQUISITION_RECORD_SCHEMA_VERSION = 1
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
SUPPORTED_MODES = {"direct-https-file", "https-tree", "https-zip-member", "manual-derived", "manual-reviewed"}


class AcquisitionError(ValueError):
    pass


def _https(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise AcquisitionError(f"{label} is required")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise AcquisitionError(f"{label} must be a credential-free HTTPS URL")
    return value


def _stable_automated_https(value: object, *, label: str) -> str:
    url = _https(value, label=label)
    parsed = urlparse(url)
    if parsed.query or parsed.fragment:
        raise AcquisitionError(f"{label} must not contain query or fragment data")
    return url


def _safe_relative(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise AcquisitionError(f"{label} must be a safe relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise AcquisitionError(f"{label} must be a safe relative POSIX path")
    return value


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AcquisitionError(f"{label} must be a positive integer")
    return value


def _host_allowed(hostname: str | None, suffixes: list[str]) -> bool:
    if not hostname:
        return False
    host = hostname.lower().rstrip(".")
    for suffix in suffixes:
        normalized = suffix.lower().lstrip(".").rstrip(".")
        if host == normalized or host.endswith("." + normalized):
            return True
    return False


def source_registry_digest(registry: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json(registry))


def load_source_registry(path: Path) -> dict[str, Any]:
    try:
        registry = require_dict(json.loads(path.read_text(encoding="utf-8")), label="artifact source registry")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise AcquisitionError(f"cannot read artifact source registry: {exc}") from exc
    validate_source_registry(registry)
    return registry


def validate_source_registry(registry: dict[str, Any]) -> None:
    schema_version = registry.get("schemaVersion")
    if schema_version not in {LEGACY_SOURCE_REGISTRY_SCHEMA_VERSION, SOURCE_REGISTRY_SCHEMA_VERSION}:
        raise AcquisitionError("unsupported artifact source registry schemaVersion")
    if not isinstance(registry.get("registryRevision"), str) or not registry["registryRevision"].strip():
        raise AcquisitionError("artifact source registryRevision is required")
    entries = require_dict(registry.get("artifacts"), label="artifact source registry artifacts")
    if not entries:
        raise AcquisitionError("artifact source registry must not be empty")
    for artifact_id, raw in entries.items():
        if not isinstance(artifact_id, str) or not artifact_id:
            raise AcquisitionError("artifact source registry IDs must be non-empty strings")
        item = require_dict(raw, label=f"artifact source registry {artifact_id}")
        mode = item.get("mode")
        if mode not in SUPPORTED_MODES:
            raise AcquisitionError(f"unsupported acquisition mode for {artifact_id}: {mode!r}")
        _https(item.get("primaryDocumentation"), label=f"{artifact_id}.primaryDocumentation")
        _safe_relative(item.get("expectedFilename"), label=f"{artifact_id}.expectedFilename")
        if not isinstance(item.get("upstreamRevision"), str) or not item["upstreamRevision"].strip():
            raise AcquisitionError(f"{artifact_id}.upstreamRevision is required")
        if mode in {"manual-derived", "manual-reviewed"}:
            locator = item.get("retrievalReference")
            if locator is not None:
                _https(locator, label=f"{artifact_id}.retrievalReference")
            continue
        hosts = require_list(item.get("allowedHostSuffixes"), label=f"{artifact_id}.allowedHostSuffixes")
        if not hosts or any(not isinstance(v, str) or not v.strip() or "." not in v.strip().lstrip(".") or not re.fullmatch(r"[A-Za-z0-9.-]+", v.strip()) for v in hosts):
            raise AcquisitionError(f"{artifact_id}.allowedHostSuffixes must contain specific DNS suffixes")
        if mode == "direct-https-file":
            url = _stable_automated_https(item.get("retrievalUrl"), label=f"{artifact_id}.retrievalUrl")
            if not _host_allowed(urlparse(url).hostname, hosts):
                raise AcquisitionError(f"{artifact_id}.retrievalUrl host is outside the allowlist")
            _positive_int(item.get("maxBytes"), label=f"{artifact_id}.maxBytes")
        elif mode == "https-zip-member":
            if schema_version != SOURCE_REGISTRY_SCHEMA_VERSION:
                raise AcquisitionError(f"{artifact_id}.https-zip-member requires source registry schemaVersion 3")
            url = _stable_automated_https(item.get("retrievalUrl"), label=f"{artifact_id}.retrievalUrl")
            if not _host_allowed(urlparse(url).hostname, hosts):
                raise AcquisitionError(f"{artifact_id}.retrievalUrl host is outside the allowlist")
            _safe_relative(item.get("archiveMember"), label=f"{artifact_id}.archiveMember")
            _positive_int(item.get("maxArchiveBytes"), label=f"{artifact_id}.maxArchiveBytes")
            _positive_int(item.get("maxBytes"), label=f"{artifact_id}.maxBytes")
            if item["maxBytes"] > item["maxArchiveBytes"]:
                raise AcquisitionError(f"{artifact_id}.maxBytes cannot exceed maxArchiveBytes")
        else:
            base = _stable_automated_https(item.get("baseUrl"), label=f"{artifact_id}.baseUrl")
            if not base.endswith("/"):
                raise AcquisitionError(f"{artifact_id}.baseUrl must end with /")
            if not _host_allowed(urlparse(base).hostname, hosts):
                raise AcquisitionError(f"{artifact_id}.baseUrl host is outside the allowlist")
            files = require_list(item.get("files"), label=f"{artifact_id}.files")
            if not files:
                raise AcquisitionError(f"{artifact_id}.files must not be empty")
            seen: set[str] = set()
            total_max = 0
            for index, raw_file in enumerate(files):
                file = require_dict(raw_file, label=f"{artifact_id}.files[{index}]")
                rel = _safe_relative(file.get("path"), label=f"{artifact_id}.files[{index}].path")
                if rel in seen:
                    raise AcquisitionError(f"{artifact_id}.files contains duplicate path: {rel}")
                seen.add(rel)
                max_bytes = _positive_int(file.get("maxBytes"), label=f"{artifact_id}.files[{index}].maxBytes")
                total_max += max_bytes
                expected = file.get("sha256")
                if expected is not None and not is_sha256(expected):
                    raise AcquisitionError(f"{artifact_id}.files[{index}].sha256 is malformed")
            if total_max > 2 * 1024 * 1024 * 1024:
                raise AcquisitionError(f"{artifact_id}.files aggregate maximum is unreasonably large")


def source_for_artifact(registry: dict[str, Any], artifact_id: str) -> dict[str, Any]:
    entries = require_dict(registry.get("artifacts"), label="artifact source registry artifacts")
    item = entries.get(artifact_id)
    if not isinstance(item, dict):
        raise AcquisitionError(f"artifact is absent from source registry: {artifact_id}")
    return item


def acquisition_record_digest(record: dict[str, Any]) -> str:
    payload = dict(record)
    payload.pop("recordSha256", None)
    return sha256_bytes(canonical_json(payload))


def validate_acquisition_record(
    record: dict[str, Any],
    *,
    registry: dict[str, Any] | None = None,
    artifact_id: str | None = None,
    artifact_path: Path | None = None,
) -> None:
    if record.get("schemaVersion") != ACQUISITION_RECORD_SCHEMA_VERSION:
        raise AcquisitionError("unsupported acquisition record schemaVersion")
    for key in ("recordId", "artifactId", "sourceRegistryRevision", "catalogRevision", "expectedFilename", "upstreamRevision"):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise AcquisitionError(f"acquisition record requires {key}")
    if artifact_id is not None and record["artifactId"] != artifact_id:
        raise AcquisitionError("acquisition record artifactId mismatch")
    if not is_sha256(record.get("sourceRegistrySha256")):
        raise AcquisitionError("acquisition record sourceRegistrySha256 is malformed")
    if not is_sha256(record.get("artifactSha256")):
        raise AcquisitionError("acquisition record artifactSha256 is malformed")
    if not is_sha256(record.get("recordSha256")) or record["recordSha256"] != acquisition_record_digest(record):
        raise AcquisitionError("acquisition record content digest mismatch")
    if not isinstance(record.get("artifactByteSize"), int) or isinstance(record.get("artifactByteSize"), bool) or record["artifactByteSize"] <= 0:
        raise AcquisitionError("acquisition record artifactByteSize must be positive")
    if not isinstance(record.get("artifactFileCount"), int) or isinstance(record.get("artifactFileCount"), bool) or record["artifactFileCount"] <= 0:
        raise AcquisitionError("acquisition record artifactFileCount must be positive")
    acquired = record.get("acquiredAtUtc")
    if not isinstance(acquired, str) or not UTC_RE.fullmatch(acquired):
        raise AcquisitionError("acquisition record acquiredAtUtc must be an ISO-8601 UTC timestamp ending in Z")
    try:
        datetime.fromisoformat(acquired[:-1] + "+00:00")
    except ValueError as exc:
        raise AcquisitionError("acquisition record acquiredAtUtc is invalid") from exc
    files = require_list(record.get("files"), label="acquisition record files")
    if not files or len(files) != record["artifactFileCount"]:
        raise AcquisitionError("acquisition record files do not match artifactFileCount")
    paths: list[str] = []
    for index, raw in enumerate(files):
        item = require_dict(raw, label=f"acquisition record files[{index}]")
        rel = _safe_relative(item.get("path"), label=f"acquisition record files[{index}].path")
        paths.append(rel)
        _stable_automated_https(item.get("requestedUrl"), label=f"acquisition record files[{index}].requestedUrl")
        _stable_automated_https(item.get("resolvedUrl"), label=f"acquisition record files[{index}].resolvedUrl")
        if not is_sha256(item.get("sha256")):
            raise AcquisitionError(f"acquisition record files[{index}].sha256 is malformed")
        _positive_int(item.get("byteSize"), label=f"acquisition record files[{index}].byteSize")
    if len(paths) != len(set(paths)):
        raise AcquisitionError("acquisition record file paths must be unique")

    if registry is not None:
        validate_source_registry(registry)
        if record["sourceRegistryRevision"] != registry["registryRevision"]:
            raise AcquisitionError("acquisition record sourceRegistryRevision mismatch")
        if record["sourceRegistrySha256"] != source_registry_digest(registry):
            raise AcquisitionError("acquisition record sourceRegistrySha256 mismatch")
        source = source_for_artifact(registry, record["artifactId"])
        if source["expectedFilename"] != record["expectedFilename"]:
            raise AcquisitionError("acquisition record expectedFilename mismatch")
        if source["upstreamRevision"] != record["upstreamRevision"]:
            raise AcquisitionError("acquisition record upstreamRevision mismatch")
        hosts = list(source.get("allowedHostSuffixes", []))
        mode = source["mode"]
        if mode not in {"direct-https-file", "https-tree", "https-zip-member"}:
            raise AcquisitionError("manual source entries cannot produce automated acquisition records")
        if mode == "direct-https-file":
            if len(files) != 1 or files[0]["requestedUrl"] != source["retrievalUrl"]:
                raise AcquisitionError("direct acquisition record does not match the registered retrieval URL")
            if paths != [source["expectedFilename"]]:
                raise AcquisitionError("direct acquisition record path mismatch")
        elif mode == "https-zip-member":
            if len(files) != 1 or files[0]["requestedUrl"] != source["retrievalUrl"]:
                raise AcquisitionError("ZIP-member acquisition record does not match the registered retrieval URL")
            if paths != [source["expectedFilename"]]:
                raise AcquisitionError("ZIP-member acquisition record path mismatch")
            container = require_dict(record.get("sourceContainer"), label="acquisition record sourceContainer")
            if container.get("kind") != "zip" or container.get("memberPath") != source["archiveMember"]:
                raise AcquisitionError("ZIP-member acquisition record sourceContainer identity mismatch")
            if not is_sha256(container.get("sha256")):
                raise AcquisitionError("ZIP-member acquisition record sourceContainer SHA-256 is malformed")
            _positive_int(container.get("byteSize"), label="acquisition record sourceContainer.byteSize")
            if container["byteSize"] > source["maxArchiveBytes"]:
                raise AcquisitionError("ZIP-member acquisition record sourceContainer exceeds registered size")
        else:
            expected_files = {str(v["path"]): v for v in source["files"]}
            if set(paths) != set(expected_files):
                raise AcquisitionError("tree acquisition record does not exactly cover registered files")
            for item in files:
                spec = expected_files[item["path"]]
                expected_url = source["baseUrl"] + item["path"]
                if item["requestedUrl"] != expected_url:
                    raise AcquisitionError("tree acquisition record requested URL mismatch")
                expected_sha = spec.get("sha256")
                if expected_sha is not None and item["sha256"] != expected_sha:
                    raise AcquisitionError(f"tree acquisition record SHA-256 mismatch for {item['path']}")
        for item in files:
            if not _host_allowed(urlparse(item["requestedUrl"]).hostname, hosts) or not _host_allowed(urlparse(item["resolvedUrl"]).hostname, hosts):
                raise AcquisitionError("acquisition record contains a URL outside the registered host allowlist")

    if artifact_path is not None:
        if not artifact_path.exists() or artifact_path.is_symlink():
            raise AcquisitionError("acquired artifact path is missing or is a symlink")
        if sha256_path(artifact_path) != record["artifactSha256"]:
            raise AcquisitionError("acquired artifact bytes do not match acquisition record")
        byte_size, file_count = artifact_stats(artifact_path)
        if (byte_size, file_count) != (record["artifactByteSize"], record["artifactFileCount"]):
            raise AcquisitionError("acquired artifact shape does not match acquisition record")
        row_bytes = 0
        for item in files:
            if artifact_path.is_file():
                local = artifact_path
            else:
                rel = PurePosixPath(item["path"])
                local = artifact_path.joinpath(*rel.parts)
            if not local.is_file() or local.is_symlink():
                raise AcquisitionError(f"acquisition record file evidence is missing locally: {item['path']}")
            local_size = local.stat().st_size
            if local_size != item["byteSize"]:
                raise AcquisitionError(f"acquisition record file byteSize mismatch: {item['path']}")
            if sha256_path(local) != item["sha256"]:
                raise AcquisitionError(f"acquisition record file SHA-256 mismatch: {item['path']}")
            row_bytes += local_size
        if row_bytes != record["artifactByteSize"]:
            raise AcquisitionError("acquisition record file evidence byte total does not match artifactByteSize")


def load_acquisition_record(
    path: Path,
    *,
    registry: dict[str, Any] | None = None,
    artifact_id: str | None = None,
    artifact_path: Path | None = None,
) -> dict[str, Any]:
    try:
        record = require_dict(json.loads(path.read_text(encoding="utf-8")), label="acquisition record")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise AcquisitionError(f"cannot read acquisition record: {exc}") from exc
    validate_acquisition_record(record, registry=registry, artifact_id=artifact_id, artifact_path=artifact_path)
    return record
