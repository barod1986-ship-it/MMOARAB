from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.catalog import load_catalog
from mte_engine.benchmark.common import sha256_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute and optionally write a SHA-256 pin for an explicitly downloaded model artifact.")
    parser.add_argument("catalog", type=Path)
    parser.add_argument("artifact_id")
    parser.add_argument("artifact_path", type=Path)
    parser.add_argument("--write", action="store_true", help="Update the catalog sha256 field atomically after hashing.")
    args = parser.parse_args()
    catalog = load_catalog(args.catalog)
    item = next((value for value in catalog["artifacts"] if value["artifactId"] == args.artifact_id), None)
    if item is None:
        raise SystemExit(f"Unknown artifactId: {args.artifact_id}")
    digest = sha256_path(args.artifact_path)
    print(json.dumps({"artifactId": args.artifact_id, "path": str(args.artifact_path), "sha256": digest}, indent=2))
    if args.write:
        item["sha256"] = digest
        temp = args.catalog.with_suffix(args.catalog.suffix + ".tmp")
        temp.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(args.catalog)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
