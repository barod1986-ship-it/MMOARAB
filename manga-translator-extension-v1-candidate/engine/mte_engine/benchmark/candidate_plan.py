from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .catalog import artifact_by_id
from .common import canonical_json, require_dict, require_list, sha256_bytes

CANDIDATE_PLAN_SCHEMA_VERSION = 1
ALLOWED_COMPONENTS = {"detector", "ocr-en", "ocr-ja", "ocr-ko", "ocr-zh", "inpaint"}


class CandidatePlanError(ValueError):
    pass


def load_candidate_plan(path: Path, *, catalog: dict[str, Any] | None = None, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        plan = require_dict(json.loads(path.read_text(encoding="utf-8")), label="candidate plan")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise CandidatePlanError(f"cannot read candidate plan: {exc}") from exc
    validate_candidate_plan(plan, catalog=catalog, policy=policy)
    return plan


def validate_candidate_plan(plan: dict[str, Any], *, catalog: dict[str, Any] | None = None, policy: dict[str, Any] | None = None) -> None:
    if plan.get("schemaVersion") != CANDIDATE_PLAN_SCHEMA_VERSION:
        raise CandidatePlanError("unsupported candidate plan schemaVersion")
    if not isinstance(plan.get("planRevision"), str) or not plan["planRevision"].strip():
        raise CandidatePlanError("candidate planRevision is required")
    candidates = require_list(plan.get("candidates"), label="candidate plan candidates")
    if not candidates or len(candidates) > 64:
        raise CandidatePlanError("candidate plan must contain 1..64 candidates")
    seen: set[str] = set()
    catalog_ids = artifact_by_id(catalog) if catalog is not None else None
    by_component: dict[str, set[str]] = {}
    for index, raw in enumerate(candidates):
        candidate = require_dict(raw, label=f"candidate plan candidates[{index}]")
        candidate_id = candidate.get("candidateId")
        component = candidate.get("component")
        family = candidate.get("family")
        artifact_ids = require_list(candidate.get("artifactIds"), label=f"candidate plan candidates[{index}].artifactIds")
        if not isinstance(candidate_id, str) or not candidate_id or candidate_id in seen:
            raise CandidatePlanError("candidate plan IDs must be unique non-empty strings")
        seen.add(candidate_id)
        if component not in ALLOWED_COMPONENTS:
            raise CandidatePlanError(f"unsupported candidate component: {component}")
        if not isinstance(family, str) or not family:
            raise CandidatePlanError("candidate family is required")
        if not artifact_ids or any(not isinstance(value, str) or not value for value in artifact_ids) or len(set(artifact_ids)) != len(artifact_ids):
            raise CandidatePlanError("candidate artifactIds must be unique non-empty strings")
        if "policyRole" in candidate and candidate["policyRole"] not in {"primary", "fallback"}:
            raise CandidatePlanError("candidate policyRole must be primary or fallback")
        by_component.setdefault(str(component), set()).add(str(family))
        if catalog_ids is not None:
            for artifact_id in artifact_ids:
                if artifact_id not in catalog_ids:
                    raise CandidatePlanError(f"candidate plan artifact is absent from catalog: {artifact_id}")
    support_ids = require_list(plan.get("supportArtifactIds", []), label="candidate plan supportArtifactIds")
    if any(not isinstance(value, str) or not value for value in support_ids) or len(set(support_ids)) != len(support_ids):
        raise CandidatePlanError("supportArtifactIds must be unique non-empty strings")
    if catalog_ids is not None:
        for artifact_id in support_ids:
            if artifact_id not in catalog_ids:
                raise CandidatePlanError(f"support artifact is absent from catalog: {artifact_id}")
    if policy is not None:
        coverage = require_dict(policy.get("candidateCoverage"), label="candidateCoverage")
        for component, raw_families in coverage.items():
            required = set(require_list(raw_families, label=f"candidateCoverage.{component}"))
            missing = required - by_component.get(component, set())
            if missing:
                raise CandidatePlanError(f"candidate plan misses required {component} families: {', '.join(sorted(missing))}")


def candidate_identity(candidate: dict[str, Any]) -> dict[str, Any]:
    result = {
        "candidateId": candidate["candidateId"],
        "component": candidate["component"],
        "family": candidate["family"],
        "artifactIds": list(candidate["artifactIds"]),
    }
    if "policyRole" in candidate:
        result["policyRole"] = candidate["policyRole"]
    return result


def plan_artifact_ids(plan: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for candidate in plan["candidates"]:
        for artifact_id in candidate["artifactIds"]:
            if artifact_id not in result:
                result.append(artifact_id)
    for artifact_id in plan.get("supportArtifactIds", []):
        if artifact_id not in result:
            result.append(artifact_id)
    return result


def compare_report_to_plan(report: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    expected = [candidate_identity(value) for value in plan["candidates"]]
    actual = [candidate_identity(value) for value in report.get("candidates", [])]
    if actual != expected:
        return ["benchmark candidate identities/artifact mapping do not exactly match the frozen candidate plan"]
    return []


def candidate_plan_digest(plan: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json(plan))
