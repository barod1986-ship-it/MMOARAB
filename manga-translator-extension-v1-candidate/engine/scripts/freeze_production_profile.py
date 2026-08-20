from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.common import canonical_json, sha256_bytes
from mte_engine.benchmark.freeze import build_freeze
from mte_engine.benchmark.source_binding import qualified_source_binding
from mte_engine.benchmark.gate import evaluate_release_gate, load_report
from mte_engine.benchmark.corpus import load_corpus


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze default-v1 only after the complete production benchmark gate passes.")
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--artifacts-dir", required=True, type=Path)
    parser.add_argument("--candidate-plan", required=True, type=Path)
    parser.add_argument("--receipts-dir", required=True, type=Path)
    parser.add_argument("--run-plan", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-head-sha", required=True)
    parser.add_argument("--repo-root", type=Path, default=ENGINE_ROOT.parent)
    args = parser.parse_args()
    gate = evaluate_release_gate(corpus_path=args.corpus, raw_path=args.raw, report_path=args.report, policy_path=args.policy, catalog_path=args.catalog, artifacts_dir=args.artifacts_dir, candidate_plan_path=args.candidate_plan, receipts_dir=args.receipts_dir, run_plan_path=args.run_plan)
    if not gate["passed"]:
        print(json.dumps(gate, ensure_ascii=False, indent=2))
        return 2
    corpus = load_corpus(args.corpus, verify_files=True)
    report = load_report(args.report)
    source_binding = qualified_source_binding(args.repo_root, source_head_sha=args.source_head_sha)
    freeze = build_freeze(gate=gate, report=report, corpus_manifest_sha256=sha256_bytes(canonical_json(corpus)), qualified_source=source_binding)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(args.output.suffix + ".tmp")
    temp.write_text(json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(args.output)
    print(json.dumps({"frozen": True, "output": str(args.output), "freezeSha256": freeze["freezeSha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
