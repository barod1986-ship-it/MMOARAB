from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.candidate_plan import load_candidate_plan, plan_artifact_ids
from mte_engine.benchmark.catalog import load_catalog
from mte_engine.benchmark.provenance import verify_receipts
from mte_engine.benchmark.gate import load_policy


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify content-addressed provenance receipts for every artifact in the production benchmark candidate plan.")
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--candidate-plan", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--artifacts-dir", required=True, type=Path)
    parser.add_argument("--receipts-dir", required=True, type=Path)
    args = parser.parse_args()
    catalog = load_catalog(args.catalog)
    policy = load_policy(args.policy)
    plan = load_candidate_plan(args.candidate_plan, catalog=catalog, policy=policy)
    artifact_ids = plan_artifact_ids(plan)
    passed, reasons, receipts = verify_receipts(catalog, artifact_ids, receipts_dir=args.receipts_dir, artifacts_dir=args.artifacts_dir)
    print(json.dumps({
        "passed": passed,
        "artifactCount": len(artifact_ids),
        "verifiedReceiptCount": len(receipts),
        "reasons": reasons,
        "receiptSha256s": {item["artifactId"]: item["receiptSha256"] for item in receipts},
    }, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
