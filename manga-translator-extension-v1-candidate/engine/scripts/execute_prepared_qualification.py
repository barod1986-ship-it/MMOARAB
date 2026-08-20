from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.common import sha256_file
from mte_engine.benchmark.dependency_locks import dependency_lock_pins
from mte_engine.benchmark.run_plan import load_run_plan
from mte_engine.benchmark.source_binding import normalize_source_head_sha

ACTIVE_POLICY = ENGINE_ROOT / "benchmark" / "policies" / "benchmark-thresholds-v3.json"
ACTIVE_CANDIDATE_PLAN = ENGINE_ROOT / "benchmark" / "candidate-plan-v3.json"
RESULT_NAMES = (
    "benchmark-raw.json",
    "benchmark-report.json",
    "benchmark-gate.json",
    "production-profile-freeze.json",
    "qualification-execution-summary.json",
)


class QualificationExecutionError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _regular(path: Path, *, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise QualificationExecutionError(f"{label} must be a regular file: {path}")
    return path


def _directory(path: Path, *, label: str) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise QualificationExecutionError(f"{label} must be a real directory: {path}")
    return path


def _run(script: str, *args: str, allowed: tuple[int, ...] = (0,)) -> int:
    command = [sys.executable, str(ENGINE_ROOT / "scripts" / script), *args]
    completed = subprocess.run(command, cwd=ENGINE_ROOT.parent, check=False)
    if completed.returncode not in allowed:
        raise QualificationExecutionError(f"{script} failed with exit code {completed.returncode}")
    return completed.returncode


def _promote_results(staging: Path, workspace: Path, *, replace: bool) -> None:
    existing = [workspace / name for name in RESULT_NAMES if (workspace / name).exists()]
    if existing and not replace:
        names = ", ".join(path.name for path in existing)
        raise QualificationExecutionError(f"qualification result files already exist ({names}); use --replace-results only after reviewing them")

    backup = workspace / ".qualification-execution-backup"
    if backup.exists():
        raise QualificationExecutionError(f"stale execution backup must be reviewed before retry: {backup}")
    backup.mkdir(mode=0o700)
    moved: list[tuple[Path, Path]] = []
    try:
        for path in existing:
            target = backup / path.name
            path.replace(target)
            moved.append((target, path))
        for name in RESULT_NAMES:
            source = staging / name
            if source.exists():
                source.replace(workspace / name)
    except Exception:
        for name in RESULT_NAMES:
            current = workspace / name
            if current.exists() and not any(destination == current for _, destination in moved):
                current.unlink(missing_ok=True)
        for source, destination in reversed(moved):
            if source.exists():
                source.replace(destination)
        raise
    finally:
        shutil.rmtree(backup, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Execute a previously prepared production qualification workspace without reacquiring or re-intaking artifacts. "
            "The benchmark review must be sealed against the exact stable runPlanSha256."
        )
    )
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--benchmark-review", required=True, type=Path)
    parser.add_argument("--replace-results", action="store_true")
    args = parser.parse_args()

    workspace = _directory(args.workspace.resolve(), label="prepared qualification workspace")
    corpus = _regular(args.corpus.resolve(), label="sealed corpus manifest")
    benchmark_review = _regular(args.benchmark_review.resolve(), label="sealed benchmark review")
    catalog = _regular(workspace / "catalog.json", label="prepared catalog")
    run_plan_path = _regular(workspace / "benchmark-run-plan.json", label="prepared benchmark run plan")
    artifacts = _directory(workspace / "artifacts", label="prepared artifacts directory")
    receipts = _directory(workspace / "receipts", label="prepared receipts directory")
    control_session_path = _regular(workspace / "qualification-control" / "qualification-session.json", label="qualification control session")
    try:
        control_session = json.loads(control_session_path.read_text(encoding="utf-8"))
        source_head_sha = normalize_source_head_sha(control_session.get("sourceHeadSha", ""))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"prepared qualification control session is invalid: {exc}")

    run_plan = load_run_plan(run_plan_path, require_ready=True)
    current_locks = dependency_lock_pins(ENGINE_ROOT.parent)
    if run_plan.get("dependencyLocks") != current_locks:
        raise SystemExit("prepared run plan is bound to different package-lock.json/engine/uv.lock bytes")

    staging = Path(tempfile.mkdtemp(prefix=f".{workspace.name}.execution-", dir=workspace.parent))
    gate_passed = False
    try:
        raw = staging / "benchmark-raw.json"
        report = staging / "benchmark-report.json"
        gate = staging / "benchmark-gate.json"
        freeze = staging / "production-profile-freeze.json"

        _run(
            "execute_benchmark.py",
            "--run-plan", str(run_plan_path),
            "--corpus", str(corpus),
            "--policy", str(ACTIVE_POLICY),
            "--catalog", str(catalog),
            "--candidate-plan", str(ACTIVE_CANDIDATE_PLAN),
            "--artifacts-dir", str(artifacts),
            "--receipts-dir", str(receipts),
            "--review", str(benchmark_review),
            "--output", str(raw),
        )
        _run("build_benchmark_report.py", "--raw", str(raw), "--policy", str(ACTIVE_POLICY), "--output", str(report))
        gate_code = _run(
            "evaluate_benchmark.py",
            "--corpus", str(corpus),
            "--raw", str(raw),
            "--report", str(report),
            "--policy", str(ACTIVE_POLICY),
            "--catalog", str(catalog),
            "--artifacts-dir", str(artifacts),
            "--candidate-plan", str(ACTIVE_CANDIDATE_PLAN),
            "--receipts-dir", str(receipts),
            "--run-plan", str(run_plan_path),
            "--output", str(gate),
            allowed=(0, 2),
        )
        gate_payload = json.loads(gate.read_text(encoding="utf-8"))
        gate_passed = gate_code == 0 and gate_payload.get("passed") is True

        if gate_passed:
            _run(
                "freeze_production_profile.py",
                "--corpus", str(corpus),
                "--raw", str(raw),
                "--report", str(report),
                "--policy", str(ACTIVE_POLICY),
                "--catalog", str(catalog),
                "--artifacts-dir", str(artifacts),
                "--candidate-plan", str(ACTIVE_CANDIDATE_PLAN),
                "--receipts-dir", str(receipts),
                "--run-plan", str(run_plan_path),
                "--output", str(freeze),
                "--source-head-sha", source_head_sha,
                "--repo-root", str(ENGINE_ROOT.parent),
            )
            _regular(freeze, label="production profile freeze")

        summary = {
            "schemaVersion": 1,
            "qualificationExecutionRevision": "rev11-prepared-qualification-execution-v1",
            "finishedAtUtc": _utc_now(),
            "runPlanSha256": run_plan["runPlanSha256"],
            "qualifiedSourceHeadSha": source_head_sha,
            "dependencyLocks": current_locks,
            "benchmarkReviewFileSha256": sha256_file(benchmark_review),
            "rawFileSha256": sha256_file(raw),
            "reportFileSha256": sha256_file(report),
            "gateFileSha256": sha256_file(gate),
            "gatePassed": gate_passed,
            "freezeFileSha256": sha256_file(freeze) if freeze.is_file() else None,
        }
        (staging / "qualification-execution-summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        _promote_results(staging, workspace, replace=args.replace_results)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if gate_passed else 2
    except (QualificationExecutionError, ValueError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"prepared qualification execution failed closed: {exc}")
    finally:
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
