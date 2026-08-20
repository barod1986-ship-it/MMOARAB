from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .common import canonical_json, is_sha256, require_dict, sha256_bytes
from .dependency_locks import validate_dependency_lock_pins
from .source_binding import validate_source_binding

FREEZE_SCHEMA_VERSION = 1
FREEZE_REVISION = "production-profile-freeze-v4-source-and-release-evidence-bound"


class FreezeError(ValueError):
    pass


def build_freeze(*, gate: dict[str, Any], report: dict[str, Any], corpus_manifest_sha256: str, qualified_source: dict[str, Any]) -> dict[str, Any]:
    if gate.get("passed") is not True:
        raise FreezeError("Release gate did not pass; production profile cannot be frozen")
    selected = require_dict(report.get("selected"), label="selected")
    runtime = require_dict(report.get("runtime"), label="runtime")
    selected_artifacts = gate.get("selectedArtifactIds")
    dependency_locks = validate_dependency_lock_pins(gate.get("dependencyLocks"))
    candidate_plan_sha256 = gate.get("candidatePlanSha256")
    run_plan_sha256 = gate.get("runPlanSha256")
    source_binding = validate_source_binding(qualified_source)
    if not isinstance(selected_artifacts, list) or not selected_artifacts:
        raise FreezeError("No selected model artifacts are pinned")
    if not is_sha256(candidate_plan_sha256):
        raise FreezeError("Production freeze requires a content-addressed candidate plan")
    if not is_sha256(run_plan_sha256):
        raise FreezeError("Production freeze requires a content-addressed benchmark run plan")
    execution = require_dict(report.get("execution"), label="execution")
    executor_source_sha256 = execution.get("executorSourceSha256")
    if not is_sha256(executor_source_sha256):
        raise FreezeError("Production freeze requires the benchmark executor source digest")
    sfx = require_dict(report.get("sfxSafety"), label="sfxSafety")
    human_review = require_dict(report.get("humanReview"), label="humanReview")
    selected_inpainter = selected.get("inpainter")
    selected_candidate = next(
        (
            item
            for item in report.get("candidates", [])
            if isinstance(item, dict) and item.get("candidateId") == selected_inpainter
        ),
        None,
    )
    if not isinstance(selected_candidate, dict):
        raise FreezeError("Selected inpainting candidate is missing from the benchmark report")
    inpaint_metrics = require_dict(selected_candidate.get("metrics"), label="selected inpainter metrics")
    freeze = {
        "schemaVersion": FREEZE_SCHEMA_VERSION,
        "freezeRevision": FREEZE_REVISION,
        "status": "approved",
        "gateRevision": gate["gateRevision"],
        "reportSha256": gate["reportSha256"],
        "policyRevision": report["policyRevision"],
        "policySha256": gate["policySha256"],
        "catalogSha256": gate["catalogSha256"],
        "candidatePlanSha256": candidate_plan_sha256,
        "runPlanSha256": run_plan_sha256,
        "executorSourceSha256": executor_source_sha256,
        "qualifiedSource": source_binding,
        "corpusManifestSha256": corpus_manifest_sha256,
        "selected": selected,
        "selectedArtifactIds": selected_artifacts,
        "selectedArtifacts": gate.get("selectedArtifacts", []),
        "runtime": runtime,
        "dependencyLocks": dependency_locks,
        "translation": report["translation"],
        "renderer": report["renderer"],
        "roleSafetyQualification": {
            "roleClassifierRevision": report["translation"].get("roleClassifierRevision"),
            "roleClassifierSfxProtectedRecall": sfx.get("roleClassifierSfxProtectedRecall"),
            "sentToTranslatorRate": sfx.get("sentToTranslatorRate"),
            "eraseInpaintMaskOverlapRate": sfx.get("eraseInpaintMaskOverlapRate"),
            "changedPixelRateAfterEncodeDecode": sfx.get("changedPixelRateAfterEncodeDecode"),
            "uncertainDestructiveEditRate": sfx.get("uncertainDestructiveEditRate"),
            "protectedConflictSilentOverwriteCount": sfx.get("protectedConflictSilentOverwriteCount"),
            "independentGroundTruthPages": sfx.get("independentGroundTruthPages"),
        },
        "inpaintingQualification": {
            "candidateId": selected_inpainter,
            "humanScore": inpaint_metrics.get("humanScore"),
            "humanCriticalFailures": inpaint_metrics.get("humanCriticalFailures"),
            "pagesReviewed": human_review.get("inpaintingPagesReviewed"),
            "criticalReviewFailures": human_review.get("criticalInpaintingFailures"),
        },
    }
    freeze["freezeSha256"] = sha256_bytes(canonical_json(freeze))
    return freeze


def validate_freeze(value: dict[str, Any]) -> bool:
    if value.get("schemaVersion") != FREEZE_SCHEMA_VERSION or value.get("freezeRevision") != FREEZE_REVISION or value.get("status") != "approved":
        return False
    try:
        validate_dependency_lock_pins(value.get("dependencyLocks"))
    except ValueError:
        return False
    expected = value.get("freezeSha256")
    if not is_sha256(expected):
        return False
    body = dict(value)
    body.pop("freezeSha256", None)
    if sha256_bytes(canonical_json(body)) != expected:
        return False
    if not isinstance(value.get("selectedArtifactIds"), list) or not value["selectedArtifactIds"]:
        return False
    pins = value.get("selectedArtifacts")
    if not isinstance(pins, list) or len(pins) != len(value["selectedArtifactIds"]):
        return False
    for pin in pins:
        if not isinstance(pin, dict) or not isinstance(pin.get("artifactId"), str) or not is_sha256(pin.get("sha256")) or not isinstance(pin.get("expectedFilename"), str):
            return False
    renderer = value.get("renderer")
    if not isinstance(renderer, dict) or not isinstance(renderer.get("fontArtifactId"), str) or not isinstance(renderer.get("adapterRevision"), str):
        return False
    translation = value.get("translation")
    if not isinstance(translation, dict) or not isinstance(translation.get("adapterId"), str) or not isinstance(translation.get("modelOrProviderRevision"), str):
        return False
    selected = value.get("selected")
    if not isinstance(selected, dict) or any(not isinstance(v, str) or not v for v in selected.values()):
        return False
    if not isinstance(value.get("policyRevision"), str) or not value["policyRevision"]:
        return False
    if not is_sha256(value.get("candidatePlanSha256")) or not is_sha256(value.get("runPlanSha256")) or not is_sha256(value.get("executorSourceSha256")):
        return False
    try:
        validate_source_binding(value.get("qualifiedSource"))
    except ValueError:
        return False
    role = value.get("roleSafetyQualification")
    if not isinstance(role, dict):
        return False
    if role.get("roleClassifierRevision") != value.get("translation", {}).get("roleClassifierRevision"):
        return False
    if role.get("roleClassifierSfxProtectedRecall") != 1.0:
        return False
    for key in (
        "sentToTranslatorRate",
        "eraseInpaintMaskOverlapRate",
        "changedPixelRateAfterEncodeDecode",
        "uncertainDestructiveEditRate",
        "protectedConflictSilentOverwriteCount",
    ):
        if role.get(key) != 0 and role.get(key) != 0.0:
            return False
    if not isinstance(role.get("independentGroundTruthPages"), int) or isinstance(role.get("independentGroundTruthPages"), bool) or role["independentGroundTruthPages"] < 10:
        return False
    inpaint = value.get("inpaintingQualification")
    if not isinstance(inpaint, dict) or inpaint.get("candidateId") != selected.get("inpainter"):
        return False
    if not isinstance(inpaint.get("humanScore"), (int, float)) or isinstance(inpaint.get("humanScore"), bool):
        return False
    if inpaint.get("humanCriticalFailures") != 0 or inpaint.get("criticalReviewFailures") != 0:
        return False
    if not isinstance(inpaint.get("pagesReviewed"), int) or isinstance(inpaint.get("pagesReviewed"), bool) or inpaint["pagesReviewed"] < 1:
        return False
    return True


def load_freeze(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) and validate_freeze(value) else None
