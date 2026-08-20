from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.execution import seal_review_draft
from mte_engine.benchmark.run_plan import load_run_plan


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seal human benchmark-review values into a content-addressed record and optionally bind them to one exact ready run plan. This never invents human scores."
    )
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--run-plan", type=Path, help="Ready benchmark run plan whose runPlanSha256 must be bound into the review.")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    draft = json.loads(args.draft.read_text(encoding="utf-8"))
    if not isinstance(draft, dict):
        raise SystemExit("review draft must be a JSON object")
    if args.run_plan is not None:
        run_plan = load_run_plan(args.run_plan, require_ready=True)
        existing = draft.get("runPlanSha256")
        if isinstance(existing, str) and existing.startswith("sha256:") and "REPLACE" not in existing and existing != run_plan["runPlanSha256"]:
            raise SystemExit("review draft already names a different runPlanSha256")
        draft["runPlanSha256"] = run_plan["runPlanSha256"]
    if not isinstance(draft.get("runPlanSha256"), str) or "REPLACE" in draft["runPlanSha256"]:
        raise SystemExit("review draft must be bound to a real runPlanSha256; pass --run-plan")
    sealed = seal_review_draft(draft)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(args.output.suffix + ".tmp")
    tmp.write_text(json.dumps(sealed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(args.output)
    print(json.dumps({"review": str(args.output), "runPlanSha256": draft["runPlanSha256"], "reviewRecordSha256": sealed["reviewRecordSha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
