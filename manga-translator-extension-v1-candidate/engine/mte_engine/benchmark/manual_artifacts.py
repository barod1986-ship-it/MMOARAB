from __future__ import annotations

import json
import math
import re
import stat
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .common import canonical_json, is_sha256, require_dict, require_list, sha256_bytes, sha256_path

POLICY_SCHEMA_VERSION = 1
DERIVATION_SCHEMA_VERSION = 1
PACKAGER_REVISION = "rev10-inpaint-onnx-packager-v1"
INPAINT_CONTRACT = "mte-onnx-inpaint-contract-v1"
CONTRACT_FILENAME = "mte-inpaint-contract.json"
DERIVATION_FILENAME = "mte-derivation.json"
MODEL_FILENAME = "model.onnx"
DEFAULT_MANUAL_POLICY = Path(__file__).resolve().parents[2] / "model-catalog" / "manual-derived-artifact-policy-v1.json"
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


class ManualArtifactError(ValueError):
    pass


def _utc(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        raise ManualArtifactError(f"{label} must be ISO-8601 UTC ending in Z")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ManualArtifactError(f"{label} is invalid") from exc
    return value


def _https(value: object, *, label: str) -> str:
    from urllib.parse import urlparse
    if not isinstance(value, str) or not value:
        raise ManualArtifactError(f"{label} is required")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ManualArtifactError(f"{label} must be a credential-free HTTPS URL without a fragment")
    return value


def load_manual_policy(path: Path) -> dict[str, Any]:
    try:
        policy = require_dict(json.loads(path.read_text(encoding="utf-8")), label="manual artifact policy")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ManualArtifactError(f"cannot read manual artifact policy: {exc}") from exc
    if policy.get("schemaVersion") != POLICY_SCHEMA_VERSION:
        raise ManualArtifactError("unsupported manual artifact policy schemaVersion")
    if policy.get("runtimeContract") != INPAINT_CONTRACT or policy.get("packagerRevision") != PACKAGER_REVISION:
        raise ManualArtifactError("manual artifact policy runtime/packager revision mismatch")
    artifacts = require_dict(policy.get("artifacts"), label="manual artifact policy artifacts")
    if set(artifacts) != {"lama-big", "aot-gan-places2"}:
        raise ManualArtifactError("manual artifact policy must exactly cover LaMa and AOT V1 artifacts")
    for artifact_id, raw in artifacts.items():
        item = require_dict(raw, label=f"manual artifact policy {artifact_id}")
        for key in ("candidateId", "expectedFilename", "upstreamProject", "primaryDocumentation", "modelFile", "imageInput", "maskInput", "output", "tensorLayout", "imageRange", "maskSemantics"):
            if not isinstance(item.get(key), str) or not item[key]:
                raise ManualArtifactError(f"manual artifact policy {artifact_id}.{key} is required")
        _https(item["primaryDocumentation"], label=f"{artifact_id}.primaryDocumentation")
        if item.get("sourceCheckpointReviewRequired") is not True or item.get("converterReviewRequired") is not True:
            raise ManualArtifactError(f"manual artifact policy {artifact_id} must require checkpoint and converter review")
        if item["modelFile"] != MODEL_FILENAME or item["tensorLayout"] != "NCHW" or item["imageRange"] != "0..1-rgb" or item["maskSemantics"] != "1=erase":
            raise ManualArtifactError(f"manual artifact policy {artifact_id} drifts from the V1 runtime tensor contract")
        pad = item.get("padMultiple")
        if isinstance(pad, bool) or not isinstance(pad, int) or not 1 <= pad <= 256:
            raise ManualArtifactError(f"manual artifact policy {artifact_id}.padMultiple is invalid")
        max_bytes = item.get("maxModelBytes")
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
            raise ManualArtifactError(f"manual artifact policy {artifact_id}.maxModelBytes is invalid")
        shapes = require_list(item.get("smokeShapes"), label=f"{artifact_id}.smokeShapes")
        if len(shapes) < 2:
            raise ManualArtifactError(f"manual artifact policy {artifact_id} needs at least two dynamic-shape smoke cases")
        for shape in shapes:
            if not isinstance(shape, list) or len(shape) != 4 or shape[0:2] != [1, 3] or any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in shape):
                raise ManualArtifactError(f"manual artifact policy {artifact_id} smoke shape is invalid")
            if shape[2] % pad or shape[3] % pad:
                raise ManualArtifactError(f"manual artifact policy {artifact_id} smoke shape is not pad-aligned")
    return policy


def load_source_checkpoint_review(path: Path, *, artifact_id: str, checkpoint: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ManualArtifactError("source checkpoint review is missing or a symlink")
    try:
        review = require_dict(json.loads(path.read_text(encoding="utf-8")), label="source checkpoint review")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ManualArtifactError(f"cannot read source checkpoint review: {exc}") from exc
    if review.get("schemaVersion") != 1 or review.get("artifactId") != artifact_id:
        raise ManualArtifactError("source checkpoint review schemaVersion/artifactId mismatch")
    for key in ("reviewRecordId", "reviewer", "upstreamRevision"):
        if not isinstance(review.get(key), str) or not review[key].strip():
            raise ManualArtifactError(f"source checkpoint review requires {key}")
    _utc(review.get("reviewedAtUtc"), label="source checkpoint review reviewedAtUtc")
    _https(review.get("retrievalUrl"), label="source checkpoint review retrievalUrl")
    if review.get("benchmarkUseStatus") != "approved" or review.get("artifactLicenseStatus") != "approved":
        raise ManualArtifactError("source checkpoint must be explicitly approved for benchmark use and artifact licensing before derivation")
    if review.get("redistributionStatus") not in {"approved", "local-only"}:
        raise ManualArtifactError("source checkpoint redistributionStatus must be approved or local-only before derivation")
    evidence = require_list(review.get("evidence"), label="source checkpoint review evidence")
    if not evidence:
        raise ManualArtifactError("source checkpoint review evidence must not be empty")
    for i, raw in enumerate(evidence):
        item = require_dict(raw, label=f"source checkpoint review evidence[{i}]")
        if not isinstance(item.get("kind"), str) or not item["kind"].strip():
            raise ManualArtifactError("source checkpoint review evidence kind is required")
        _https(item.get("url"), label=f"source checkpoint review evidence[{i}].url")
    expected = review.get("sourceCheckpointSha256")
    if not is_sha256(expected):
        raise ManualArtifactError("source checkpoint review sourceCheckpointSha256 is malformed")
    if checkpoint.is_symlink() or not checkpoint.exists():
        raise ManualArtifactError("source checkpoint is missing or a symlink")
    actual = sha256_path(checkpoint)
    if actual != expected:
        raise ManualArtifactError("source checkpoint bytes do not match reviewed SHA-256")
    return review


def load_converter_review(
    path: Path,
    *,
    artifact_id: str,
    converter_source: Path,
    converter_source_url: str,
    converter_revision: str,
) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ManualArtifactError("converter review is missing or a symlink")
    try:
        review = require_dict(json.loads(path.read_text(encoding="utf-8")), label="converter review")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ManualArtifactError(f"cannot read converter review: {exc}") from exc
    if review.get("schemaVersion") != 1 or review.get("artifactId") != artifact_id:
        raise ManualArtifactError("converter review schemaVersion/artifactId mismatch")
    for key in ("reviewRecordId", "reviewer", "converterRevision"):
        if not isinstance(review.get(key), str) or not review[key].strip():
            raise ManualArtifactError(f"converter review requires {key}")
    _utc(review.get("reviewedAtUtc"), label="converter review reviewedAtUtc")
    reviewed_url = _https(review.get("converterSourceUrl"), label="converter review converterSourceUrl")
    from urllib.parse import urlparse
    if urlparse(reviewed_url).query:
        raise ManualArtifactError("converter review converterSourceUrl must not contain a query string")
    if reviewed_url != converter_source_url or review.get("converterRevision") != converter_revision:
        raise ManualArtifactError("converter review URL/revision does not match the requested converter source")
    if review.get("converterUseStatus") != "approved" or review.get("converterLicenseStatus") != "approved":
        raise ManualArtifactError("converter must be explicitly approved for production derivation and licensing")
    evidence = require_list(review.get("evidence"), label="converter review evidence")
    if not evidence:
        raise ManualArtifactError("converter review evidence must not be empty")
    for i, raw in enumerate(evidence):
        item = require_dict(raw, label=f"converter review evidence[{i}]")
        if not isinstance(item.get("kind"), str) or not item["kind"].strip():
            raise ManualArtifactError("converter review evidence kind is required")
        _https(item.get("url"), label=f"converter review evidence[{i}].url")
    expected = review.get("converterSourceSha256")
    if not is_sha256(expected):
        raise ManualArtifactError("converter review converterSourceSha256 is malformed")
    if converter_source.is_symlink() or not converter_source.exists():
        raise ManualArtifactError("converter source is missing or a symlink")
    if sha256_path(converter_source) != expected:
        raise ManualArtifactError("converter source bytes do not match reviewed SHA-256")
    return review


def derivation_digest(payload: dict[str, Any]) -> str:
    body = dict(payload)
    body.pop("derivationSha256", None)
    return sha256_bytes(canonical_json(body))


def validate_derivation_manifest(data: dict[str, Any], *, artifact_id: str | None = None) -> None:
    if data.get("schemaVersion") != DERIVATION_SCHEMA_VERSION or data.get("packagerRevision") != PACKAGER_REVISION:
        raise ManualArtifactError("unsupported inpainting derivation manifest")
    if artifact_id is not None and data.get("artifactId") != artifact_id:
        raise ManualArtifactError("inpainting derivation artifactId mismatch")
    for key in ("artifactId", "candidateId", "runtimeContract", "sourceReviewRecordId", "converterReviewRecordId", "converterRevision", "operator"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ManualArtifactError(f"inpainting derivation requires {key}")
    created_at = data.get("createdAtUtc")
    if not isinstance(created_at, str) or not created_at.endswith("Z"):
        raise ManualArtifactError("inpainting derivation createdAtUtc must be an explicit UTC timestamp")
    try:
        datetime.fromisoformat(created_at[:-1] + "+00:00")
    except ValueError as exc:
        raise ManualArtifactError("inpainting derivation createdAtUtc is malformed") from exc
    runtime_validation = data.get("runtimeValidation")
    if not isinstance(runtime_validation, dict) or runtime_validation.get("validatedProvider") != "CPUExecutionProvider":
        raise ManualArtifactError("inpainting derivation runtimeValidation must record validated CPUExecutionProvider")
    smoke_shapes = runtime_validation.get("smokeShapes")
    if not isinstance(smoke_shapes, list) or not smoke_shapes or any(not isinstance(shape, list) or len(shape) != 4 or any(not isinstance(v, int) or v <= 0 for v in shape) for shape in smoke_shapes):
        raise ManualArtifactError("inpainting derivation runtimeValidation smokeShapes are malformed")
    if data["runtimeContract"] != INPAINT_CONTRACT:
        raise ManualArtifactError("inpainting derivation runtimeContract mismatch")
    for key in ("sourceArtifactSha256", "sourceReviewFileSha256", "converterReviewFileSha256", "converterSourceSha256", "modelSha256", "derivationSha256"):
        if not is_sha256(data.get(key)):
            raise ManualArtifactError(f"inpainting derivation {key} is malformed")
    converter_url = _https(data.get("converterSourceUrl"), label="inpainting derivation converterSourceUrl")
    from urllib.parse import urlparse
    if urlparse(converter_url).query:
        raise ManualArtifactError("inpainting derivation converterSourceUrl must not contain a query string")
    if data["derivationSha256"] != derivation_digest(data):
        raise ManualArtifactError("inpainting derivation content digest mismatch")


def _safe_zip_name(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or normalized.startswith("/") or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ManualArtifactError("derived inpainting ZIP contains an unsafe path")
    return path


def inspect_inpaint_package(path: Path, *, artifact_id: str, expected_candidate_id: str | None = None) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ManualArtifactError("derived inpainting package is missing or a symlink")
    policy = load_manual_policy(DEFAULT_MANUAL_POLICY)
    if artifact_id not in policy["artifacts"]:
        raise ManualArtifactError("derived inpainting artifactId is outside the active manual policy")
    policy_item = policy["artifacts"][artifact_id]
    policy_candidate_id = policy_item["candidateId"]
    if expected_candidate_id is not None and expected_candidate_id != policy_candidate_id:
        raise ManualArtifactError("requested inpainting candidateId conflicts with active manual policy")
    try:
        zf = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ManualArtifactError("derived inpainting package is not a valid ZIP") from exc
    with zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        names: list[str] = []
        for info in infos:
            rel = _safe_zip_name(info.filename)
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise ManualArtifactError("derived inpainting ZIP may not contain symlinks")
            names.append(rel.as_posix())
        if sorted(names) != sorted([MODEL_FILENAME, CONTRACT_FILENAME, DERIVATION_FILENAME]):
            raise ManualArtifactError("derived inpainting ZIP must contain exactly model.onnx, mte-inpaint-contract.json and mte-derivation.json")
        info_by_name = {info.filename.replace("\\", "/"): info for info in infos}
        if info_by_name[CONTRACT_FILENAME].file_size > 1024 * 1024 or info_by_name[DERIVATION_FILENAME].file_size > 1024 * 1024:
            raise ManualArtifactError("derived inpainting ZIP metadata exceeds the 1 MiB bound")
        if info_by_name[MODEL_FILENAME].file_size <= 0 or info_by_name[MODEL_FILENAME].file_size > int(policy_item["maxModelBytes"]):
            raise ManualArtifactError("derived inpainting ONNX model is outside the active policy size bound")
        try:
            contract = require_dict(json.loads(zf.read(CONTRACT_FILENAME)), label="inpainting contract")
            derivation = require_dict(json.loads(zf.read(DERIVATION_FILENAME)), label="inpainting derivation")
            digest = __import__("hashlib").sha256()
            with zf.open(MODEL_FILENAME, "r") as model_stream:
                while chunk := model_stream.read(1024 * 1024):
                    digest.update(chunk)
        except (KeyError, json.JSONDecodeError, ValueError) as exc:
            raise ManualArtifactError(f"derived inpainting ZIP metadata is invalid: {exc}") from exc
    validate_derivation_manifest(derivation, artifact_id=artifact_id)
    if derivation.get("candidateId") != policy_candidate_id:
        raise ManualArtifactError("derived inpainting candidateId mismatch with active manual policy")
    if derivation.get("runtimeValidation", {}).get("smokeShapes") != policy_item["smokeShapes"]:
        raise ManualArtifactError("derived inpainting runtime smoke evidence drifts from active manual policy")
    expected = {
        "schemaVersion": 1,
        "contract": INPAINT_CONTRACT,
        "candidateId": derivation["candidateId"],
        "modelFile": MODEL_FILENAME,
        "imageInput": "image",
        "maskInput": "mask",
        "output": "output",
        "tensorLayout": "NCHW",
        "imageRange": "0..1-rgb",
        "maskSemantics": "1=erase",
    }
    for key, value in expected.items():
        if contract.get(key) != value:
            raise ManualArtifactError(f"derived inpainting contract field mismatch: {key}")
    if contract.get("padMultiple") != policy_item["padMultiple"]:
        raise ManualArtifactError("derived inpainting contract padMultiple drifts from active manual policy")
    model_sha = "sha256:" + digest.hexdigest()
    if contract.get("modelSha256") != model_sha or derivation.get("modelSha256") != model_sha:
        raise ManualArtifactError("derived inpainting package model SHA-256 mismatch")
    derivation_bytes_sha = "sha256:" + __import__("hashlib").sha256(canonical_json(derivation)).hexdigest()
    if contract.get("derivationManifestSha256") != derivation_bytes_sha:
        raise ManualArtifactError("derived inpainting contract derivation manifest SHA-256 mismatch")
    return {"contract": contract, "derivation": derivation, "modelSha256": model_sha, "packageSha256": sha256_path(path)}


def validate_onnx_runtime(model_path: Path, policy_item: dict[str, Any], *, session_factory: Callable[[str, list[str]], Any] | None = None) -> dict[str, Any]:
    if model_path.is_symlink() or not model_path.is_file():
        raise ManualArtifactError("ONNX model is missing or a symlink")
    if model_path.stat().st_size <= 0 or model_path.stat().st_size > int(policy_item["maxModelBytes"]):
        raise ManualArtifactError("ONNX model size is outside the manual-derived policy bound")
    try:
        import numpy as np
    except ImportError as exc:
        raise ManualArtifactError("NumPy is required to validate derived ONNX artifacts") from exc
    if session_factory is None:
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise ManualArtifactError("ONNX Runtime is required to validate derived ONNX artifacts") from exc
        def session_factory(path: str, providers: list[str]):
            opts = ort.SessionOptions()
            return ort.InferenceSession(path, sess_options=opts, providers=providers)
    try:
        session = session_factory(str(model_path), ["CPUExecutionProvider"])
    except Exception as exc:
        raise ManualArtifactError(f"ONNX Runtime refused the derived model: {exc}") from exc
    inputs = {i.name: i for i in session.get_inputs()}
    outputs = {o.name: o for o in session.get_outputs()}
    for name in (policy_item["imageInput"], policy_item["maskInput"]):
        if name not in inputs:
            raise ManualArtifactError(f"derived ONNX model is missing required input {name}")
    if policy_item["output"] not in outputs:
        raise ManualArtifactError("derived ONNX model is missing required output")
    for shape in policy_item["smokeShapes"]:
        _, _, h, w = shape
        image = np.zeros((1, 3, h, w), dtype=np.float32)
        image[:, :, :, :] = 0.25
        mask = np.zeros((1, 1, h, w), dtype=np.float32)
        mask[:, :, h//4:3*h//4, w//4:3*w//4] = 1.0
        try:
            result = session.run([policy_item["output"]], {policy_item["imageInput"]: image, policy_item["maskInput"]: mask})[0]
        except Exception as exc:
            raise ManualArtifactError(f"derived ONNX smoke inference failed at {h}x{w}: {exc}") from exc
        arr = np.asarray(result)
        if arr.shape != image.shape or not np.isfinite(arr).all():
            raise ManualArtifactError(f"derived ONNX smoke output is invalid at {h}x{w}")
    return {"validatedProvider": "CPUExecutionProvider", "smokeShapes": policy_item["smokeShapes"]}
