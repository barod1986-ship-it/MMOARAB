from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .benchmark.catalog import resolve_artifact_path
from .benchmark.common import sha256_path
from .benchmark.freeze import load_freeze
from .config import EngineSettings
from .errors import EngineApiError
from .pipeline.detector import PADDLE_DETECTOR_CANDIDATES, ProductionDetector
from .pipeline.inpaint import ProductionInpainter, SUPPORTED_INPAINT_CANDIDATES
from .pipeline.ocr import OCR_CANDIDATE_ARTIFACT, ProductionOcrRouter, production_ocr_candidates_supported
from .pipeline.reading_order import HeuristicReadingOrder
from .pipeline.renderer import ArabicRenderer
from .pipeline.roles import PRODUCTION_ROLE_REVISION, VisualEnclosureRoleClassifier
from .pipeline.staged import StagedPipeline
from .pipeline.translator import OpenAIResponsesTranslator, production_translation_support


# Runtime support is intentionally explicit. A benchmark winner not listed here is
# not silently substituted with a different implementation.
SUPPORTED_ROLE_CLASSIFIER_REVISIONS: frozenset[str] = frozenset({PRODUCTION_ROLE_REVISION})

_MAX_ARCHIVE_FILES = 8192
_MAX_EXTRACTED_BYTES = 8 * 1024 * 1024 * 1024


def materialize_model_directory(settings: EngineSettings, *, artifact_id: str, source: Path, expected_sha256: str) -> Path:
    """Return a local model directory without trusting archive paths or remote loaders.

    Directory artifacts are used in place. Reviewed tar/zip bytes are extracted once
    into a digest-addressed cache under the Engine data directory. Symlinks, links,
    device entries, traversal and oversized archives are refused.
    """
    if source.is_symlink():
        raise EngineApiError("model_not_ready", f"Frozen model artifact may not be a symlink: {artifact_id}.", 409)
    if source.is_dir():
        if sha256_path(source) != expected_sha256:
            raise EngineApiError("model_not_ready", f"Frozen model directory digest changed: {artifact_id}.", 409)
        return source
    if not source.is_file() or sha256_path(source) != expected_sha256:
        raise EngineApiError("model_not_ready", f"Frozen model artifact digest changed: {artifact_id}.", 409)
    lower = source.name.lower()
    archive_kind = "zip" if lower.endswith(".zip") else "tar" if lower.endswith((".tar", ".tar.gz", ".tgz")) else None
    if archive_kind is None:
        raise EngineApiError("model_not_ready", f"Frozen model artifact must be a local directory or reviewed tar/zip archive: {artifact_id}.", 409)
    digest = expected_sha256.removeprefix("sha256:")
    cache_parent = settings.data_dir / "runtime-models" / artifact_id
    target = cache_parent / digest
    marker = target / ".mte-artifact.json"
    if target.is_dir() and marker.is_file():
        try:
            meta = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = None
        if meta == {"schemaVersion": 1, "artifactId": artifact_id, "sourceSha256": expected_sha256}:
            return _select_materialized_model_root(target)
    cache_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".extract-", dir=cache_parent))
    try:
        if archive_kind == "zip":
            _safe_extract_zip(source, staging)
        else:
            _safe_extract_tar(source, staging)
        (staging / ".mte-artifact.json").write_text(
            json.dumps({"schemaVersion": 1, "artifactId": artifact_id, "sourceSha256": expected_sha256}, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        if target.exists():
            shutil.rmtree(target)
        os.replace(staging, target)
        staging = target  # ownership transferred; finalizer below should not delete it
        return _select_materialized_model_root(target)
    finally:
        if staging.exists() and staging != target:
            shutil.rmtree(staging, ignore_errors=True)


def _select_materialized_model_root(target: Path) -> Path:
    children = [p for p in target.iterdir() if p.name != ".mte-artifact.json"]
    directories = [p for p in children if p.is_dir() and not p.is_symlink()]
    files = [p for p in children if p.is_file()]
    if len(directories) == 1 and not files:
        return directories[0]
    return target


def _safe_archive_relative(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or normalized.startswith("/") or path.is_absolute() or ".." in path.parts or any(part in {"", "."} for part in path.parts):
        raise EngineApiError("model_not_ready", "Model archive contains an unsafe path.", 409)
    return path


def _safe_extract_zip(source: Path, staging: Path) -> None:
    count = 0
    total = 0
    try:
        zf = zipfile.ZipFile(source)
    except (OSError, zipfile.BadZipFile) as exc:
        raise EngineApiError("model_not_ready", "Frozen ZIP model artifact is invalid.", 409) from exc
    with zf:
        for info in zf.infolist():
            rel = _safe_archive_relative(info.filename.rstrip("/"))
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise EngineApiError("model_not_ready", "Model ZIP may not contain symlinks.", 409)
            count += 1
            total += int(info.file_size)
            if count > _MAX_ARCHIVE_FILES or total > _MAX_EXTRACTED_BYTES:
                raise EngineApiError("model_not_ready", "Model ZIP exceeds extraction safety bounds.", 409)
            destination = staging.joinpath(*rel.parts)
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, destination.open("xb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)


def _safe_extract_tar(source: Path, staging: Path) -> None:
    count = 0
    total = 0
    try:
        tf = tarfile.open(source, mode="r:*")
    except (OSError, tarfile.TarError) as exc:
        raise EngineApiError("model_not_ready", "Frozen TAR model artifact is invalid.", 409) from exc
    with tf:
        for member in tf:
            rel = _safe_archive_relative(member.name.rstrip("/"))
            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                raise EngineApiError("model_not_ready", "Model TAR may contain only regular files/directories.", 409)
            if not (member.isfile() or member.isdir()):
                raise EngineApiError("model_not_ready", "Model TAR contains an unsupported entry type.", 409)
            count += 1
            total += int(member.size)
            if count > _MAX_ARCHIVE_FILES or total > _MAX_EXTRACTED_BYTES:
                raise EngineApiError("model_not_ready", "Model TAR exceeds extraction safety bounds.", 409)
            destination = staging.joinpath(*rel.parts)
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(member)
            if src is None:
                raise EngineApiError("model_not_ready", "Model TAR regular file could not be read.", 409)
            with src, destination.open("xb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)



@dataclass(frozen=True, slots=True)
class ProductionRuntimeAssessment:
    state: str
    reasons: tuple[str, ...]
    text_leaves_device: bool


def assess_production_runtime(settings: EngineSettings, freeze: dict[str, Any]) -> ProductionRuntimeAssessment:
    reasons: list[str] = []
    selected = freeze.get("selected")
    if not isinstance(selected, dict):
        return ProductionRuntimeAssessment("runtime-unavailable", ("production freeze has no selected candidate map",), False)

    detector = selected.get("detector")
    if detector not in PADDLE_DETECTOR_CANDIDATES:
        reasons.append(f"detector runtime adapter is not implemented: {detector!r}")
    elif importlib.util.find_spec("paddleocr") is None:
        reasons.append("PaddleOCR production dependency is not installed")

    ocr_ok, ocr_reason = production_ocr_candidates_supported(selected)
    if not ocr_ok and ocr_reason:
        reasons.append(ocr_reason)
    else:
        if importlib.util.find_spec("paddleocr") is None:
            reasons.append("PaddleOCR production OCR dependency is not installed")
        if selected.get("ocrJapanese") == "manga-ocr-ja" and importlib.util.find_spec("manga_ocr") is None:
            reasons.append("manga-ocr production dependency is not installed")

    translation = freeze.get("translation")
    translation_ok, translation_reason, text_leaves_device = production_translation_support(translation)
    if not translation_ok and translation_reason:
        reasons.append(translation_reason)

    role_revision = translation.get("roleClassifierRevision") if isinstance(translation, dict) else None
    if role_revision not in SUPPORTED_ROLE_CLASSIFIER_REVISIONS:
        reasons.append(
            f"role/SFX classifier runtime is not production-approved: {role_revision!r}; "
            "unhinted detector regions must remain protected"
        )

    inpainter = selected.get("inpainter")
    if inpainter not in SUPPORTED_INPAINT_CANDIDATES:
        reasons.append(f"frozen inpainting runtime adapter is not implemented: {inpainter!r}")
    elif importlib.util.find_spec("onnxruntime") is None:
        reasons.append("ONNX Runtime production inpainting dependency is not installed")

    if reasons:
        return ProductionRuntimeAssessment("runtime-unavailable", tuple(dict.fromkeys(reasons)), text_leaves_device)

    if text_leaves_device:
        if not settings.external_text_translation_enabled:
            return ProductionRuntimeAssessment("misconfigured-provider", ("external OCR-text translation is not explicitly enabled",), True)
        if not settings.openai_api_key:
            return ProductionRuntimeAssessment("misconfigured-provider", ("OpenAI API key is not configured",), True)

    return ProductionRuntimeAssessment("ready", (), text_leaves_device)


def frozen_artifact_paths(settings: EngineSettings, freeze: dict[str, Any]) -> dict[str, Path]:
    if settings.model_artifacts_dir is None:
        raise EngineApiError("model_not_ready", "Production model artifact directory is not configured.", 409)
    pins = freeze.get("selectedArtifacts")
    if not isinstance(pins, list):
        raise EngineApiError("model_not_ready", "Production freeze has no selected artifact pins.", 409)
    paths: dict[str, Path] = {}
    for pin in pins:
        if not isinstance(pin, dict):
            continue
        artifact_id = pin.get("artifactId")
        filename = pin.get("expectedFilename")
        if not isinstance(artifact_id, str) or not isinstance(filename, str):
            continue
        try:
            paths[artifact_id] = resolve_artifact_path(settings.model_artifacts_dir, filename, artifact_id=artifact_id)
        except ValueError as exc:
            raise EngineApiError("model_not_ready", f"Unsafe frozen model artifact path: {artifact_id}.", 409) from exc
    return paths


def build_production_pipeline(settings: EngineSettings) -> StagedPipeline:
    freeze_path = settings.production_freeze_path or (Path(__file__).resolve().parent / "benchmark" / "production-profile-freeze.json")
    freeze = load_freeze(freeze_path)
    if freeze is None:
        raise EngineApiError("profile_not_ready", "Production benchmark freeze is missing or invalid.", 409)
    assessment = assess_production_runtime(settings, freeze)
    if assessment.state != "ready":
        raise EngineApiError("profile_not_ready", "; ".join(assessment.reasons) or "Production runtime is not ready.", 409)
    if settings.arabic_font_path is None:
        raise EngineApiError("renderer_capability_missing", "Arabic font profile is not configured.", 409)

    selected = freeze["selected"]
    assert isinstance(selected, dict)
    artifacts = frozen_artifact_paths(settings, freeze)
    detector_id = str(selected["detector"])
    detector_artifact = PADDLE_DETECTOR_CANDIDATES[detector_id]
    detector_source = artifacts.get(detector_artifact)
    detector_pin = next((pin for pin in freeze["selectedArtifacts"] if isinstance(pin, dict) and pin.get("artifactId") == detector_artifact), None)
    if detector_source is None or not isinstance(detector_pin, dict) or not isinstance(detector_pin.get("sha256"), str):
        raise EngineApiError("model_not_ready", f"Frozen detector artifact is absent: {detector_artifact}.", 409)
    detector_path = materialize_model_directory(settings, artifact_id=detector_artifact, source=detector_source, expected_sha256=str(detector_pin["sha256"]))

    runtime_artifacts = dict(artifacts)
    for candidate_id in {str(selected.get(key, "")) for key in ("ocrEnglish", "ocrJapanese", "ocrKorean", "ocrChinese")}:
        artifact_id = OCR_CANDIDATE_ARTIFACT.get(candidate_id)
        if not artifact_id or artifact_id not in runtime_artifacts:
            continue
        pin = next((item for item in freeze["selectedArtifacts"] if isinstance(item, dict) and item.get("artifactId") == artifact_id), None)
        if isinstance(pin, dict) and isinstance(pin.get("sha256"), str):
            runtime_artifacts[artifact_id] = materialize_model_directory(settings, artifact_id=artifact_id, source=runtime_artifacts[artifact_id], expected_sha256=str(pin["sha256"]))

    inpainter_candidate = str(selected["inpainter"])
    inpainter_artifact = {"lama-inpaint": "lama-big", "aot-inpaint": "aot-gan-places2"}.get(inpainter_candidate)
    if not inpainter_artifact:
        raise EngineApiError("model_not_ready", f"Frozen inpainting candidate has no artifact mapping: {inpainter_candidate}.", 409)
    inpainter_source = runtime_artifacts.get(inpainter_artifact)
    inpainter_pin = next((item for item in freeze["selectedArtifacts"] if isinstance(item, dict) and item.get("artifactId") == inpainter_artifact), None)
    if inpainter_source is None or not isinstance(inpainter_pin, dict) or not isinstance(inpainter_pin.get("sha256"), str):
        raise EngineApiError("model_not_ready", f"Frozen inpainting artifact is absent: {inpainter_artifact}.", 409)
    inpainter_path = materialize_model_directory(
        settings, artifact_id=inpainter_artifact, source=inpainter_source, expected_sha256=str(inpainter_pin["sha256"])
    )

    translation = freeze["translation"]
    assert isinstance(translation, dict)
    translator = OpenAIResponsesTranslator(
        api_key=settings.openai_api_key or "",
        model=str(translation["modelOrProviderRevision"]),
    )
    renderer = ArabicRenderer(settings.arabic_font_path)
    renderer.self_test()

    # All production adapters below are now implemented, but this path is reachable
    # only after the benchmark freeze pins the exact role revision, model artifacts,
    # inpainting winner and provider policy. Missing dependencies/artifacts fail closed.
    return StagedPipeline(
        detector=ProductionDetector(candidate_id=detector_id, model_path=detector_path),
        reading_order=HeuristicReadingOrder(),
        ocr=ProductionOcrRouter(selected={str(k): str(v) for k, v in selected.items()}, artifact_paths=runtime_artifacts),
        roles=VisualEnclosureRoleClassifier(),
        translator=translator,
        inpainter=ProductionInpainter(candidate_id=inpainter_candidate, model_dir=inpainter_path),
        renderer=renderer,
    )
