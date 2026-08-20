from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.catalog import artifact_by_id, load_catalog, resolve_artifact_path
from mte_engine.benchmark.candidate_plan import load_candidate_plan, plan_artifact_ids
from mte_engine.benchmark.common import is_sha256, sha256_path
from mte_engine.benchmark.gate import load_policy


def _unresolved(item: dict, *, artifacts_dir: Path | None) -> list[str]:
    reasons: list[str] = []
    artifact_id = str(item["artifactId"])
    if item.get("benchmarkUseStatus") != "approved":
        reasons.append("benchmark-use")
    if item.get("artifactLicenseStatus") != "approved":
        reasons.append("artifact-license")
    if item.get("redistributionStatus") not in {"approved", "local-only"}:
        reasons.append("redistribution/provisioning")
    sha = item.get("sha256")
    if not is_sha256(sha):
        reasons.append("sha256")
    elif artifacts_dir is not None:
        path = resolve_artifact_path(artifacts_dir, str(item["expectedFilename"]), artifact_id=artifact_id)
        if not path.exists():
            reasons.append("local-bytes")
        elif sha256_path(path) != sha:
            reasons.append("local-digest")
    return reasons


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate model provenance/license/hash catalog.")
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--artifacts-dir", type=Path)
    parser.add_argument("--candidate-plan", type=Path, help="Scope release readiness to the exact planned V1 artifacts.")
    parser.add_argument("--policy", type=Path, help="Required with --candidate-plan so candidate coverage is validated.")
    parser.add_argument("--require-local-hashes", action="store_true")
    args = parser.parse_args()

    if bool(args.candidate_plan) != bool(args.policy):
        parser.error("--candidate-plan and --policy must be supplied together")

    # Catalog structure is always validated globally. Release readiness is scoped
    # to the active immutable candidate plan so blocked post-V1 research entries
    # cannot be confused with V1 shipping blockers.
    catalog = load_catalog(args.catalog, artifacts_dir=args.artifacts_dir)
    by_id = artifact_by_id(catalog)
    all_ids = set(by_id)
    if args.candidate_plan:
        policy = load_policy(args.policy)
        plan = load_candidate_plan(args.candidate_plan, catalog=catalog, policy=policy)
        release_ids = set(plan_artifact_ids(plan))
    else:
        release_ids = all_ids

    unresolved: dict[str, list[str]] = {}
    for artifact_id in sorted(release_ids):
        reasons = _unresolved(by_id[artifact_id], artifacts_dir=args.artifacts_dir)
        if reasons:
            unresolved[artifact_id] = reasons

    output = {
        "catalogRevision": catalog["catalogRevision"],
        "artifactCount": len(catalog["artifacts"]),
        "releaseScope": "candidate-plan" if args.candidate_plan else "all-catalog-artifacts",
        "releaseArtifactIds": sorted(release_ids),
        "releaseUnresolvedArtifactIds": sorted(unresolved),
        "releaseUnresolvedReasons": unresolved,
        "researchExcludedArtifactIds": sorted(all_ids - release_ids),
    }
    print(json.dumps(output, indent=2))
    return 2 if args.require_local_hashes and unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
