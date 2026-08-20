from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.gate import evaluate_release_gate


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the REV10 production ML release gate.")
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--artifacts-dir", required=True, type=Path)
    parser.add_argument("--candidate-plan", required=True, type=Path)
    parser.add_argument("--receipts-dir", required=True, type=Path)
    parser.add_argument("--run-plan", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    gate = evaluate_release_gate(corpus_path=args.corpus, raw_path=args.raw, report_path=args.report, policy_path=args.policy, catalog_path=args.catalog, artifacts_dir=args.artifacts_dir, candidate_plan_path=args.candidate_plan, receipts_dir=args.receipts_dir, run_plan_path=args.run_plan)
    payload = json.dumps(gate, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if gate["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
