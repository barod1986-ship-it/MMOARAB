from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.candidate_plan import candidate_plan_digest, load_candidate_plan, plan_artifact_ids
from mte_engine.benchmark.catalog import artifact_by_id, load_catalog, resolve_artifact_path
from mte_engine.benchmark.common import canonical_json, is_sha256, sha256_bytes, sha256_path
from mte_engine.benchmark.corpus import load_corpus, production_corpus_gate, validate_corpus
from mte_engine.benchmark.gate import load_policy
from mte_engine.benchmark.provenance import verify_receipts
from mte_engine.benchmark.execution import executor_pin
from mte_engine.benchmark.dependency_locks import dependency_lock_pins


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a tamper-evident benchmark run plan after corpus, candidate identities, local artifact bytes and provenance receipts are validated.")
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--candidate-plan", required=True, type=Path)
    parser.add_argument("--artifacts-dir", required=True, type=Path)
    parser.add_argument("--receipts-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    reasons: list[str] = []
    corpus = load_corpus(args.corpus, verify_files=True)
    corpus_summary = validate_corpus(corpus, base_dir=args.corpus.parent, verify_files=True)
    corpus_ok, corpus_reasons = production_corpus_gate(corpus_summary)
    reasons.extend(corpus_reasons)
    policy = load_policy(args.policy)
    catalog = load_catalog(args.catalog)
    plan = load_candidate_plan(args.candidate_plan, catalog=catalog, policy=policy)
    artifact_ids = plan_artifact_ids(plan)
    receipts_ok, receipt_reasons, receipts = verify_receipts(catalog, artifact_ids, receipts_dir=args.receipts_dir, artifacts_dir=args.artifacts_dir)
    reasons.extend(receipt_reasons)

    by_id = artifact_by_id(catalog)
    artifact_pins: list[dict] = []
    for artifact_id in artifact_ids:
        item = by_id[artifact_id]
        if item.get("benchmarkUseStatus") != "approved":
            reasons.append(f"benchmark use is not approved for planned artifact: {artifact_id}")
        if not is_sha256(item.get("sha256")):
            reasons.append(f"planned artifact has no SHA-256 pin: {artifact_id}")
            continue
        path = resolve_artifact_path(args.artifacts_dir, str(item["expectedFilename"]), artifact_id=artifact_id)
        if not path.exists() or sha256_path(path) != item["sha256"]:
            reasons.append(f"planned local artifact is missing or hash-mismatched: {artifact_id}")
        artifact_pins.append({"artifactId": artifact_id, "sha256": item["sha256"], "expectedFilename": item["expectedFilename"]})

    receipt_map = {item["artifactId"]: item["receiptSha256"] for item in receipts}
    plan_payload = {
        "schemaVersion": 2,
        "runPlanRevision": "rev11-production-benchmark-run-plan-v3",
        "createdAtUtc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "ready": bool(corpus_ok and receipts_ok and not reasons),
        "reasons": sorted(set(reasons)),
        "corpusId": corpus["corpusId"],
        "corpusManifestSha256": sha256_bytes(canonical_json(corpus)),
        "policyRevision": policy["policyRevision"],
        "policySha256": sha256_bytes(canonical_json(policy)),
        "catalogRevision": catalog["catalogRevision"],
        "catalogSha256": sha256_bytes(canonical_json(catalog)),
        "candidatePlanRevision": plan["planRevision"],
        "candidatePlanSha256": candidate_plan_digest(plan),
        "executor": executor_pin(ENGINE_ROOT),
        "dependencyLocks": dependency_lock_pins(ENGINE_ROOT.parent),
        "artifactPins": artifact_pins,
        "artifactReceiptSha256s": receipt_map,
    }
    plan_payload["runPlanSha256"] = sha256_bytes(canonical_json(plan_payload))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(args.output.suffix + ".tmp")
    tmp.write_text(json.dumps(plan_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(args.output)
    print(json.dumps(plan_payload, ensure_ascii=False, indent=2))
    return 0 if plan_payload["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
