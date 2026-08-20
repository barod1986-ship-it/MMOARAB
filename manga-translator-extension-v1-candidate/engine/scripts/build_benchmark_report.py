from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.gate import load_policy  # noqa: E402
from mte_engine.benchmark.report_builder import build_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize raw benchmark measurements, recompute metrics, and deterministically select candidates.")
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raw = json.loads(args.raw.read_text(encoding="utf-8"))
    policy = load_policy(args.policy)
    report = build_report(raw, policy)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.output), "selected": report["selected"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
