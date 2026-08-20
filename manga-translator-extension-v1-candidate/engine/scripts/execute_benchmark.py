from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.execution import execute_benchmark  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute the frozen REV10 benchmark run-plan and emit tamper-evident raw schema-v2 evidence.")
    parser.add_argument("--run-plan", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--candidate-plan", required=True, type=Path)
    parser.add_argument("--artifacts-dir", required=True, type=Path)
    parser.add_argument("--receipts-dir", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raw = execute_benchmark(
        run_plan_path=args.run_plan,
        corpus_path=args.corpus,
        policy_path=args.policy,
        catalog_path=args.catalog,
        candidate_plan_path=args.candidate_plan,
        artifacts_dir=args.artifacts_dir,
        receipts_dir=args.receipts_dir,
        review_path=args.review,
        output_path=args.output,
    )
    print(json.dumps({"raw": str(args.output), "evidenceSha256": raw["execution"]["evidenceSha256"], "executorSourceSha256": raw["execution"]["executorSourceSha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
