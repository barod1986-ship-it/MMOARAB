from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .catalog import artifact_by_id, resolve_artifact_path
from .common import canonical_json, is_sha256, require_dict, require_list, sha256_bytes, sha256_path

RECEIPT_SCHEMA_VERSION = 1
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
ALLOWED_ACQUISITION_METHODS = {"manual-download", "official-cli", "local-conversion", "local-copy"}
ALLOWED_DECISIONS = {"approved", "pending", "blocked"}
ALLOWED_REDISTRIBUTION = {"approved", "local-only", "pending", "blocked"}


class ProvenanceError(ValueError):
    pass


def _utc(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        raise ProvenanceError(f"{label} must be an ISO-8601 UTC timestamp ending in Z")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ProvenanceError(f"{label} is not a valid timestamp") from exc
    return value


def _https(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProvenanceError(f"{label} is required")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ProvenanceError(f"{label} must be a credential-free HTTPS URL")
    return value


def artifact_stats(path: Path) -> tuple[int, int]:
    if path.is_symlink():
        raise ProvenanceError("symlink artifacts are refused")
    if path.is_file():
        return path.stat().st_size, 1
    if not path.is_dir():
        raise ProvenanceError("artifact path does not exist")
    total = 0
    count = 0
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            raise ProvenanceError("symlink artifacts are refused")
        if item.is_file():
            total += item.stat().st_size
            count += 1
        elif not item.is_dir():
            raise ProvenanceError("non-regular artifact entries are refused")
    if count == 0:
        raise ProvenanceError("artifact directory is empty")
    return total, count


def receipt_digest(receipt: dict[str, Any]) -> str:
    payload = dict(receipt)
    payload.pop("receiptSha256", None)
    return sha256_bytes(canonical_json(payload))


def load_receipt(path: Path, *, catalog: dict[str, Any] | None = None, artifacts_dir: Path | None = None) -> dict[str, Any]:
    try:
        receipt = require_dict(json.loads(path.read_text(encoding="utf-8")), label="artifact receipt")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ProvenanceError(f"cannot read artifact receipt: {exc}") from exc
    validate_receipt(receipt, catalog=catalog, artifacts_dir=artifacts_dir, receipt_dir=path.parent)
    return receipt


def validate_receipt(receipt: dict[str, Any], *, catalog: dict[str, Any] | None = None, artifacts_dir: Path | None = None, receipt_dir: Path | None = None) -> None:
    if receipt.get("schemaVersion") != RECEIPT_SCHEMA_VERSION:
        raise ProvenanceError("unsupported artifact receipt schemaVersion")
    for key in ("receiptId", "artifactId", "catalogRevision", "expectedFilename"):
        if not isinstance(receipt.get(key), str) or not receipt[key].strip():
            raise ProvenanceError(f"artifact receipt requires {key}")
    if not is_sha256(receipt.get("artifactSha256")):
        raise ProvenanceError("artifactSha256 is malformed")
    if not is_sha256(receipt.get("receiptSha256")) or receipt["receiptSha256"] != receipt_digest(receipt):
        raise ProvenanceError("artifact receipt content digest mismatch")
    if isinstance(receipt.get("artifactByteSize"), bool) or not isinstance(receipt.get("artifactByteSize"), int) or receipt["artifactByteSize"] <= 0:
        raise ProvenanceError("artifactByteSize must be a positive integer")
    if isinstance(receipt.get("artifactFileCount"), bool) or not isinstance(receipt.get("artifactFileCount"), int) or receipt["artifactFileCount"] <= 0:
        raise ProvenanceError("artifactFileCount must be a positive integer")

    acquisition = receipt.get("acquisition")
    if acquisition is not None:
        acquisition = require_dict(acquisition, label="receipt.acquisition")
        for key in ("recordFilename", "sourceRegistryRevision"):
            if not isinstance(acquisition.get(key), str) or not acquisition[key].strip():
                raise ProvenanceError(f"receipt.acquisition.{key} is required")
        record_filename = acquisition["recordFilename"]
        if Path(record_filename).name != record_filename or not record_filename.endswith(".acquisition.json"):
            raise ProvenanceError("receipt.acquisition.recordFilename must be a safe sibling acquisition filename")
        for key in ("recordFileSha256", "recordContentSha256", "sourceRegistrySha256"):
            if not is_sha256(acquisition.get(key)):
                raise ProvenanceError(f"receipt.acquisition.{key} is malformed")
        if receipt_dir is not None:
            record_path = receipt_dir / record_filename
            if not record_path.is_file() or record_path.is_symlink():
                raise ProvenanceError("receipt acquisition record is missing")
            try:
                from .acquisition import load_acquisition_record
                record = load_acquisition_record(record_path, artifact_id=str(receipt["artifactId"]))
            except (ValueError, OSError) as exc:
                raise ProvenanceError(f"receipt acquisition record is invalid: {exc}") from exc
            if sha256_path(record_path) != acquisition["recordFileSha256"]:
                raise ProvenanceError("receipt acquisition record file digest mismatch")
            if record.get("recordSha256") != acquisition["recordContentSha256"]:
                raise ProvenanceError("receipt acquisition record content digest mismatch")
            if record["sourceRegistryRevision"] != acquisition["sourceRegistryRevision"] or record["sourceRegistrySha256"] != acquisition["sourceRegistrySha256"]:
                raise ProvenanceError("receipt acquisition registry pin mismatch")
            if record["artifactSha256"] != receipt["artifactSha256"]:
                raise ProvenanceError("receipt acquisition artifact digest mismatch")
            if record.get("catalogRevision") != receipt["catalogRevision"]:
                raise ProvenanceError("receipt acquisition catalog revision mismatch")
            if record.get("expectedFilename") != receipt["expectedFilename"]:
                raise ProvenanceError("receipt acquisition expected filename mismatch")

    source = require_dict(receipt.get("source"), label="receipt.source")
    _https(source.get("provenanceUrl"), label="receipt.source.provenanceUrl")
    _https(source.get("retrievalUrl"), label="receipt.source.retrievalUrl")
    if not isinstance(source.get("upstreamRevision"), str) or not source["upstreamRevision"].strip():
        raise ProvenanceError("receipt.source.upstreamRevision is required")
    if source.get("acquisitionMethod") not in ALLOWED_ACQUISITION_METHODS:
        raise ProvenanceError("receipt.source.acquisitionMethod is invalid")
    if acquisition is not None and source.get("acquisitionMethod") != "official-cli":
        raise ProvenanceError("receipt with an automated acquisition record must use official-cli acquisitionMethod")
    _utc(source.get("acquiredAtUtc"), label="receipt.source.acquiredAtUtc")

    review = require_dict(receipt.get("review"), label="receipt.review")
    if review.get("reviewed") is not True:
        raise ProvenanceError("receipt.review.reviewed must be true")
    for key in ("reviewer", "reviewRecordId"):
        if not isinstance(review.get(key), str) or not review[key].strip():
            raise ProvenanceError(f"receipt.review.{key} is required")
    _utc(review.get("reviewedAtUtc"), label="receipt.review.reviewedAtUtc")
    if review.get("benchmarkUseStatus") not in ALLOWED_DECISIONS:
        raise ProvenanceError("receipt.review.benchmarkUseStatus is invalid")
    if review.get("artifactLicenseStatus") not in ALLOWED_DECISIONS:
        raise ProvenanceError("receipt.review.artifactLicenseStatus is invalid")
    if review.get("redistributionStatus") not in ALLOWED_REDISTRIBUTION:
        raise ProvenanceError("receipt.review.redistributionStatus is invalid")
    evidence = require_list(review.get("evidence"), label="receipt.review.evidence")
    if not evidence:
        raise ProvenanceError("receipt.review.evidence must not be empty")
    for index, raw in enumerate(evidence):
        item = require_dict(raw, label=f"receipt.review.evidence[{index}]")
        if not isinstance(item.get("kind"), str) or not item["kind"].strip():
            raise ProvenanceError("review evidence kind is required")
        _https(item.get("url"), label=f"receipt.review.evidence[{index}].url")

    if catalog is not None:
        by_id = artifact_by_id(catalog)
        artifact = by_id.get(str(receipt["artifactId"]))
        if artifact is None:
            raise ProvenanceError("receipt artifactId is absent from catalog")
        if receipt["catalogRevision"] != catalog.get("catalogRevision"):
            raise ProvenanceError("receipt catalogRevision does not match catalog")
        if receipt["expectedFilename"] != artifact.get("expectedFilename"):
            raise ProvenanceError("receipt expectedFilename does not match catalog")
        if source["provenanceUrl"] != artifact.get("sourceUrl"):
            raise ProvenanceError("receipt provenanceUrl does not match catalog sourceUrl")
        if source["upstreamRevision"] != artifact.get("upstreamRevision"):
            raise ProvenanceError("receipt upstreamRevision does not match catalog")
        if receipt["artifactSha256"] != artifact.get("sha256"):
            raise ProvenanceError("receipt artifactSha256 does not match catalog pin")
        for field in ("benchmarkUseStatus", "artifactLicenseStatus", "redistributionStatus"):
            if review[field] != artifact.get(field):
                raise ProvenanceError(f"receipt review {field} does not match catalog")
        runtime_contract = artifact.get("runtimeContract")
        derivation = receipt.get("derivation")
        if runtime_contract is not None:
            if not isinstance(derivation, dict):
                raise ProvenanceError("derived runtime artifact requires derivation provenance")
            if derivation.get("runtimeContract") != runtime_contract:
                raise ProvenanceError("derivation runtimeContract does not match catalog")
            if derivation.get("packagerRevision") != "rev10-inpaint-onnx-packager-v1":
                raise ProvenanceError("derivation packagerRevision is not the production V1 packager")
            for field in ("sourceArtifactSha256", "sourceReviewFileSha256", "converterReviewFileSha256", "converterSourceSha256", "modelSha256", "derivationSha256"):
                if not is_sha256(derivation.get(field)):
                    raise ProvenanceError(f"derivation {field} is required")
            for field in ("sourceReviewRecordId", "converterReviewRecordId", "converterRevision"):
                if not isinstance(derivation.get(field), str) or not derivation[field].strip():
                    raise ProvenanceError(f"derivation {field} is required")
            _https(derivation.get("converterSourceUrl"), label="receipt.derivation.converterSourceUrl")

        if artifacts_dir is not None:
            artifact_path = resolve_artifact_path(artifacts_dir, str(artifact["expectedFilename"]), artifact_id=str(artifact["artifactId"]))
            if not artifact_path.exists() or sha256_path(artifact_path) != receipt["artifactSha256"]:
                raise ProvenanceError("receipt does not match local artifact bytes")
            byte_size, file_count = artifact_stats(artifact_path)
            if byte_size != receipt["artifactByteSize"] or file_count != receipt["artifactFileCount"]:
                raise ProvenanceError("receipt artifact size/file-count does not match local artifact")
            if runtime_contract == "mte-onnx-inpaint-contract-v1":
                try:
                    from .manual_artifacts import inspect_inpaint_package
                    inspected = inspect_inpaint_package(artifact_path, artifact_id=str(artifact["artifactId"]))
                except (ValueError, OSError) as exc:
                    raise ProvenanceError(f"derived inpainting package is invalid: {exc}") from exc
                packaged = inspected["derivation"]
                for field in ("runtimeContract", "packagerRevision", "sourceArtifactSha256", "sourceReviewRecordId", "sourceReviewFileSha256", "converterReviewRecordId", "converterReviewFileSha256", "converterRevision", "converterSourceUrl", "converterSourceSha256", "modelSha256", "derivationSha256"):
                    if derivation.get(field) != packaged.get(field):
                        raise ProvenanceError(f"receipt derivation does not match packaged derivation: {field}")


def receipt_path(receipts_dir: Path, artifact_id: str) -> Path:
    if not artifact_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for ch in artifact_id):
        raise ProvenanceError("artifactId is unsafe for receipt filename")
    return receipts_dir / f"{artifact_id}.receipt.json"


def verify_receipts(catalog: dict[str, Any], artifact_ids: list[str], *, receipts_dir: Path, artifacts_dir: Path) -> tuple[bool, list[str], list[dict[str, Any]]]:
    reasons: list[str] = []
    receipts: list[dict[str, Any]] = []
    for artifact_id in sorted(set(artifact_ids)):
        path = receipt_path(receipts_dir, artifact_id)
        if not path.is_file():
            reasons.append(f"artifact provenance receipt is missing: {artifact_id}")
            continue
        try:
            receipt = load_receipt(path, catalog=catalog, artifacts_dir=artifacts_dir)
            receipts.append(receipt)
        except (ProvenanceError, OSError, ValueError) as exc:
            reasons.append(f"artifact provenance receipt is invalid for {artifact_id}: {exc}")
    return not reasons, reasons, receipts
