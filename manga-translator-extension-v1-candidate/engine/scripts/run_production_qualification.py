from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.acquisition import load_source_registry, source_for_artifact
from mte_engine.benchmark.candidate_plan import load_candidate_plan, plan_artifact_ids
from mte_engine.benchmark.catalog import artifact_by_id, load_catalog
from mte_engine.benchmark.corpus import load_corpus, production_corpus_gate, validate_corpus
from mte_engine.benchmark.gate import load_policy
from mte_engine.benchmark.manual_artifacts import inspect_inpaint_package, load_manual_policy
from mte_engine.benchmark.run_plan import load_run_plan
from mte_engine.benchmark.common import is_sha256
from mte_engine.benchmark.qualification_bundle import validate_artifact_review

ACTIVE_CATALOG = ENGINE_ROOT / "model-catalog" / "model-candidates-v1.json"
ACTIVE_SOURCE_REGISTRY = ENGINE_ROOT / "model-catalog" / "acquisition-source-registry-v3.json"
ACTIVE_MANUAL_POLICY = ENGINE_ROOT / "model-catalog" / "manual-derived-artifact-policy-v1.json"
ACTIVE_POLICY = ENGINE_ROOT / "benchmark" / "policies" / "benchmark-thresholds-v3.json"
ACTIVE_CANDIDATE_PLAN = ENGINE_ROOT / "benchmark" / "candidate-plan-v3.json"
AUTOMATED_MODES = {"direct-https-file", "https-tree", "https-zip-member"}
EXPECTED_AUTOMATED = {
    "ppocrv6-small-det",
    "ppocrv6-medium-det",
    "ppocrv6-small-rec",
    "ppocrv6-medium-rec",
    "ppocrv5-korean-mobile-rec",
    "manga-ocr-base-0.1.16",
    "noto-sans-arabic-production-font",
}
EXPECTED_MANUAL = {"lama-big", "aot-gan-places2"}


class QualificationError(RuntimeError):
    pass


def _run(script: str, *args: str) -> None:
    command = [sys.executable, str(ENGINE_ROOT / "scripts" / script), *args]
    completed = subprocess.run(command, cwd=ENGINE_ROOT.parent, check=False)
    if completed.returncode != 0:
        raise QualificationError(f"{script} failed with exit code {completed.returncode}")


def _review_path(reviews_dir: Path, artifact_id: str) -> Path:
    path = reviews_dir / f"{artifact_id}.review.json"
    if not path.is_file() or path.is_symlink():
        raise QualificationError(f"missing reviewed artifact decision: {path}")
    return path


def _preflight_review(path: Path, artifact_id: str) -> None:
    validate_artifact_review(path, artifact_id)


def _require_file_or_dir(path: Path, *, label: str) -> Path:
    if not path.exists() or path.is_symlink():
        raise QualificationError(f"{label} is missing or is a symlink: {path}")
    return path


def _promote(staging: Path, workspace: Path, *, replace: bool) -> None:
    backup = workspace.with_name(workspace.name + ".mte-backup")
    if backup.exists():
        raise QualificationError(f"stale qualification backup must be reviewed before retry: {backup}")
    backed_up = False
    try:
        if workspace.exists():
            if not replace:
                raise QualificationError("qualification workspace already exists; use --replace only after reviewing it")
            workspace.replace(backup)
            backed_up = True
        staging.replace(workspace)
    except Exception:
        if workspace.exists() and workspace != staging:
            if workspace.is_dir():
                shutil.rmtree(workspace, ignore_errors=True)
            else:
                workspace.unlink(missing_ok=True)
        if backed_up and backup.exists():
            backup.replace(workspace)
        raise
    else:
        if backup.exists():
            if backup.is_dir():
                shutil.rmtree(backup)
            else:
                backup.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare one stable, fail-closed production ML qualification workspace: validate the real corpus and all human artifact decisions, "
            "acquire exactly the seven allowlisted automated artifacts when requested, intake reviewed LaMa/AOT packages, and seal a ready run plan. "
            "Benchmark execution is intentionally a separate step so its human review can bind the exact runPlanSha256."
        )
    )
    parser.add_argument("--workspace", required=True, type=Path, help="Output qualification workspace. Built transactionally.")
    parser.add_argument("--corpus", required=True, type=Path, help="Sealed schema-v2 production corpus manifest with rights-chain evidence.")
    parser.add_argument("--artifact-reviews-dir", required=True, type=Path, help="Contains <artifactId>.review.json final human decisions.")
    parser.add_argument("--manual-artifacts-dir", required=True, type=Path, help="Reviewed manual/derived LaMa and AOT runtime packages.")
    parser.add_argument("--acquired-dir", type=Path, help="Previously acquired automated-source bytes when --download-automated is not used.")
    parser.add_argument("--acquisition-records-dir", type=Path, help="Previously generated automated acquisition records.")
    parser.add_argument("--download-automated", action="store_true", help="Perform allowlisted network acquisition for all seven automated primary-source artifacts.")
    parser.add_argument("--input-bundle-sha256", help="Verified REV13 qualification input bundle SHA-256 binding for the preparation attestation.")
    parser.add_argument("--replace", action="store_true", help="Transactionally replace an existing prepared workspace.")
    args = parser.parse_args()

    if args.input_bundle_sha256 is not None and not is_sha256(args.input_bundle_sha256):
        raise SystemExit("--input-bundle-sha256 must be a sha256: digest produced by verify_qualification_input_bundle.py")
    workspace = args.workspace.resolve()
    workspace.parent.mkdir(parents=True, exist_ok=True)
    if not args.download_automated and (args.acquired_dir is None or args.acquisition_records_dir is None):
        raise SystemExit("without --download-automated, --acquired-dir and --acquisition-records-dir are required")

    corpus_path = _require_file_or_dir(args.corpus.resolve(), label="sealed corpus manifest")
    reviews_dir = _require_file_or_dir(args.artifact_reviews_dir.resolve(), label="artifact reviews directory")
    manual_dir = _require_file_or_dir(args.manual_artifacts_dir.resolve(), label="manual artifacts directory")

    base_catalog = load_catalog(ACTIVE_CATALOG)
    policy = load_policy(ACTIVE_POLICY)
    candidate_plan = load_candidate_plan(ACTIVE_CANDIDATE_PLAN, catalog=base_catalog, policy=policy)
    artifact_ids = plan_artifact_ids(candidate_plan)
    by_id = artifact_by_id(base_catalog)
    source_registry = load_source_registry(ACTIVE_SOURCE_REGISTRY)

    automated_ids = {artifact_id for artifact_id in artifact_ids if str(source_for_artifact(source_registry, artifact_id)["mode"]) in AUTOMATED_MODES}
    manual_ids = set(artifact_ids) - automated_ids
    if automated_ids != EXPECTED_AUTOMATED or manual_ids != EXPECTED_MANUAL:
        raise SystemExit(
            "active V1 qualification artifact topology drifted: expected exactly seven automated artifacts and reviewed LaMa/AOT manual artifacts"
        )

    # Fail before network access when the corpus, review decisions, or manual runtime packages are not actually ready.
    corpus = load_corpus(corpus_path, verify_files=True)
    corpus_summary = validate_corpus(corpus, base_dir=corpus_path.parent, verify_files=True)
    corpus_ok, corpus_reasons = production_corpus_gate(corpus_summary)
    if not corpus_ok:
        raise SystemExit("production corpus preflight failed: " + "; ".join(corpus_reasons))
    for artifact_id in artifact_ids:
        _preflight_review(_review_path(reviews_dir, artifact_id), artifact_id)
    manual_policy = load_manual_policy(ACTIVE_MANUAL_POLICY)
    for artifact_id in sorted(manual_ids):
        item = by_id[artifact_id]
        source_path = _require_file_or_dir(manual_dir / str(item["expectedFilename"]), label=f"reviewed manual artifact {artifact_id}")
        policy_item = manual_policy["artifacts"].get(artifact_id)
        if not isinstance(policy_item, dict):
            raise QualificationError(f"manual artifact policy is missing {artifact_id}")
        inspect_inpaint_package(source_path, artifact_id=artifact_id, expected_candidate_id=str(policy_item["candidateId"]))

    staging = Path(tempfile.mkdtemp(prefix=f".{workspace.name}.staging-", dir=workspace.parent))
    try:
        catalog_path = staging / "catalog.json"
        shutil.copyfile(ACTIVE_CATALOG, catalog_path)
        artifacts_dir = staging / "artifacts"
        receipts_dir = staging / "receipts"
        acquired_dir = staging / "acquired" if args.download_automated else args.acquired_dir.resolve()
        acquisition_records_dir = staging / "acquisition-records" if args.download_automated else args.acquisition_records_dir.resolve()
        if args.download_automated:
            acquired_dir.mkdir(parents=True, exist_ok=True)
            acquisition_records_dir.mkdir(parents=True, exist_ok=True)

        intake_summary: list[dict[str, str]] = []
        for artifact_id in artifact_ids:
            catalog_item = by_id[artifact_id]
            source = source_for_artifact(source_registry, artifact_id)
            review = _review_path(reviews_dir, artifact_id)
            expected_name = str(catalog_item["expectedFilename"])
            mode = str(source["mode"])
            automated = mode in AUTOMATED_MODES
            if automated and args.download_automated:
                _run(
                    "acquire_official_artifact.py",
                    "--catalog", str(catalog_path),
                    "--source-registry", str(ACTIVE_SOURCE_REGISTRY),
                    "--artifact-id", artifact_id,
                    "--output-dir", str(acquired_dir),
                    "--records-dir", str(acquisition_records_dir),
                    "--download",
                )
            source_path = (acquired_dir / expected_name) if automated else (manual_dir / expected_name)
            _require_file_or_dir(source_path, label=f"artifact {artifact_id}")
            command = [
                "--catalog", str(catalog_path),
                "--artifact-id", artifact_id,
                "--source", str(source_path),
                "--review", str(review),
                "--artifacts-dir", str(artifacts_dir),
                "--receipts-dir", str(receipts_dir),
                "--commit",
            ]
            if automated:
                record = acquisition_records_dir / f"{artifact_id}.acquisition.json"
                _require_file_or_dir(record, label=f"acquisition record {artifact_id}")
                command.extend(["--source-registry", str(ACTIVE_SOURCE_REGISTRY), "--acquisition-record", str(record)])
            _run("intake_model_artifact.py", *command)
            intake_summary.append({"artifactId": artifact_id, "mode": mode, "intakeClass": "automated-primary-source" if automated else "reviewed-manual-derived"})

        run_plan_path = staging / "benchmark-run-plan.json"
        _run(
            "prepare_benchmark_run.py",
            "--corpus", str(corpus_path),
            "--policy", str(ACTIVE_POLICY),
            "--catalog", str(catalog_path),
            "--candidate-plan", str(ACTIVE_CANDIDATE_PLAN),
            "--artifacts-dir", str(artifacts_dir),
            "--receipts-dir", str(receipts_dir),
            "--output", str(run_plan_path),
        )
        run_plan = load_run_plan(run_plan_path, require_ready=True)
        summary = {
            "schemaVersion": 1,
            "qualificationRevision": "rev13-production-qualification-prepare-v3",
            "candidatePlanRevision": candidate_plan["planRevision"],
            "policyRevision": policy["policyRevision"],
            "corpusId": corpus["corpusId"],
            "downloadAutomated": args.download_automated,
            "qualificationInputBundleSha256": args.input_bundle_sha256,
            "automatedArtifactCount": len(automated_ids),
            "manualArtifactCount": len(manual_ids),
            "runPlanSha256": run_plan["runPlanSha256"],
            "dependencyLocks": run_plan["dependencyLocks"],
            "artifacts": intake_summary,
            "outputs": {"runPlan": "benchmark-run-plan.json"},
            "nextStep": "seal a benchmark review against this exact runPlanSha256, then execute_prepared_qualification.py",
        }
        (staging / "qualification-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _promote(staging, workspace, replace=args.replace)
        print(json.dumps({"qualifiedWorkspace": str(workspace), **summary}, ensure_ascii=False, indent=2))
        return 0
    except (QualificationError, ValueError, OSError) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise SystemExit(f"production qualification preparation failed closed: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
