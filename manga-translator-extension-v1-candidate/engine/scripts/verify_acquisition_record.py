from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.acquisition import load_acquisition_record, load_source_registry, source_for_artifact  # noqa: E402
from mte_engine.benchmark.catalog import artifact_by_id, load_catalog  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-verify an acquired production artifact against its source registry, acquisition record, catalog identity, local bytes and file shape. No network access is performed.")
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--source-registry", required=True, type=Path)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--record", required=True, type=Path)
    args = parser.parse_args()

    catalog = load_catalog(args.catalog)
    artifact = artifact_by_id(catalog).get(args.artifact_id)
    if artifact is None:
        raise SystemExit(f"Unknown artifactId: {args.artifact_id}")
    registry = load_source_registry(args.source_registry)
    source = source_for_artifact(registry, args.artifact_id)
    if source["expectedFilename"] != artifact["expectedFilename"] or source["upstreamRevision"] != artifact["upstreamRevision"]:
        raise SystemExit("source registry identity does not match catalog")
    record = load_acquisition_record(args.record, registry=registry, artifact_id=args.artifact_id, artifact_path=args.artifact)
    if record.get("catalogRevision") != catalog["catalogRevision"]:
        raise SystemExit("acquisition record catalogRevision mismatch")
    print(json.dumps({
        "artifactId": args.artifact_id,
        "artifactSha256": record["artifactSha256"],
        "recordSha256": record["recordSha256"],
        "sourceRegistryRevision": record["sourceRegistryRevision"],
        "catalogRevision": record["catalogRevision"],
        "verified": True,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
