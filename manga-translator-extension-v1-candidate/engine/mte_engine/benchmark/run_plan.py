from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .common import canonical_json, is_sha256, require_dict, require_list, sha256_bytes
from .dependency_locks import validate_dependency_lock_pins

RUN_PLAN_SCHEMA_VERSION = 2
RUN_PLAN_REVISION = "rev11-production-benchmark-run-plan-v3"


class RunPlanError(ValueError):
    pass


def run_plan_digest(plan: dict[str, Any]) -> str:
    payload = dict(plan)
    payload.pop("runPlanSha256", None)
    return sha256_bytes(canonical_json(payload))


def load_run_plan(path: Path, *, require_ready: bool = True) -> dict[str, Any]:
    try:
        plan = require_dict(json.loads(path.read_text(encoding="utf-8")), label="benchmark run plan")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise RunPlanError(f"cannot read benchmark run plan: {exc}") from exc
    validate_run_plan(plan, require_ready=require_ready)
    return plan


def validate_run_plan(plan: dict[str, Any], *, require_ready: bool = True) -> None:
    if plan.get("schemaVersion") != RUN_PLAN_SCHEMA_VERSION or plan.get("runPlanRevision") != RUN_PLAN_REVISION:
        raise RunPlanError("unsupported benchmark run plan schema/revision")
    if require_ready and plan.get("ready") is not True:
        raise RunPlanError("benchmark run plan is not ready")
    reasons = require_list(plan.get("reasons"), label="benchmark run plan reasons")
    if plan.get("ready") is True and reasons:
        raise RunPlanError("ready benchmark run plan may not contain blockers")
    for key in ("corpusManifestSha256", "policySha256", "catalogSha256", "candidatePlanSha256", "runPlanSha256"):
        if not is_sha256(plan.get(key)):
            raise RunPlanError(f"benchmark run plan {key} is malformed")
    if plan["runPlanSha256"] != run_plan_digest(plan):
        raise RunPlanError("benchmark run plan content digest mismatch")
    executor = require_dict(plan.get("executor"), label="benchmark run plan executor")
    validate_dependency_lock_pins(plan.get("dependencyLocks"))
    if executor.get("revision") != "rev10-production-benchmark-executor-v1":
        raise RunPlanError("benchmark run plan executor revision is unsupported")
    if not is_sha256(executor.get("sourceSha256")):
        raise RunPlanError("benchmark run plan executor source digest is malformed")
    pins = require_list(plan.get("artifactPins"), label="benchmark run plan artifactPins")
    receipt_map = require_dict(plan.get("artifactReceiptSha256s"), label="benchmark run plan artifactReceiptSha256s")
    seen: set[str] = set()
    for index, raw in enumerate(pins):
        item = require_dict(raw, label=f"artifactPins[{index}]")
        artifact_id = item.get("artifactId")
        if not isinstance(artifact_id, str) or not artifact_id or artifact_id in seen:
            raise RunPlanError("benchmark run plan artifact IDs must be unique")
        seen.add(artifact_id)
        if not is_sha256(item.get("sha256")):
            raise RunPlanError(f"benchmark run plan artifact pin is malformed: {artifact_id}")
        if not isinstance(item.get("expectedFilename"), str) or not item["expectedFilename"]:
            raise RunPlanError(f"benchmark run plan expectedFilename is missing: {artifact_id}")
        if not is_sha256(receipt_map.get(artifact_id)):
            raise RunPlanError(f"benchmark run plan receipt pin is missing: {artifact_id}")
    if set(receipt_map) != seen:
        raise RunPlanError("benchmark run plan receipt map must exactly match artifact pins")
