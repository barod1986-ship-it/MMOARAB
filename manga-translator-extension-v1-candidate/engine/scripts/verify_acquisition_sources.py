from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.acquisition import load_source_registry, source_for_artifact, source_registry_digest  # noqa: E402
from mte_engine.benchmark.candidate_plan import load_candidate_plan  # noqa: E402
from mte_engine.benchmark.catalog import artifact_by_id, load_catalog  # noqa: E402
from mte_engine.benchmark.gate import load_policy  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify that every active V1 ML/support artifact has a primary-source acquisition identity that exactly matches the catalog and candidate plan. No network access is performed.")
    parser.add_argument("--catalog", type=Path, default=ENGINE_ROOT / "model-catalog" / "model-candidates-v1.json")
    parser.add_argument("--source-registry", type=Path, default=ENGINE_ROOT / "model-catalog" / "acquisition-source-registry-v3.json")
    parser.add_argument("--candidate-plan", type=Path, default=ENGINE_ROOT / "benchmark" / "candidate-plan-v3.json")
    parser.add_argument("--policy", type=Path, default=ENGINE_ROOT / "benchmark" / "policies" / "benchmark-thresholds-v3.json")
    args = parser.parse_args()

    catalog = load_catalog(args.catalog)
    policy = load_policy(args.policy)
    plan = load_candidate_plan(args.candidate_plan, catalog=catalog, policy=policy)
    registry = load_source_registry(args.source_registry)
    by_id = artifact_by_id(catalog)

    planned: list[str] = []
    for candidate in plan["candidates"]:
        planned.extend(candidate["artifactIds"])
    planned.extend(plan.get("supportArtifactIds", []))
    active_ids = sorted(set(planned))

    automated: list[str] = []
    manual: list[str] = []
    for artifact_id in active_ids:
        artifact = by_id[artifact_id]
        source = source_for_artifact(registry, artifact_id)
        if source["expectedFilename"] != artifact["expectedFilename"]:
            raise SystemExit(f"source registry expectedFilename mismatch: {artifact_id}")
        if source["upstreamRevision"] != artifact["upstreamRevision"]:
            raise SystemExit(f"source registry upstreamRevision mismatch: {artifact_id}")
        if source["mode"] in {"direct-https-file", "https-tree", "https-zip-member"}:
            automated.append(artifact_id)
        else:
            manual.append(artifact_id)

    research_excluded = sorted(
        artifact_id for artifact_id in registry["artifacts"]
        if artifact_id not in active_ids and artifact_id in by_id
    )
    result = {
        "schemaVersion": 1,
        "catalogRevision": catalog["catalogRevision"],
        "policyRevision": policy["policyRevision"],
        "candidatePlanRevision": plan["planRevision"],
        "sourceRegistryRevision": registry["registryRevision"],
        "sourceRegistrySha256": source_registry_digest(registry),
        "activeArtifactCount": len(active_ids),
        "automatedPrimarySourceArtifactIds": automated,
        "manualArtifactIds": manual,
        "researchExcludedArtifactIds": research_excluded,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
