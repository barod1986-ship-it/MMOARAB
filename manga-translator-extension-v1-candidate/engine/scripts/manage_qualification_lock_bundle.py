from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.common import sha256_file
from mte_engine.benchmark.dependency_locks import dependency_lock_pins
from mte_engine.benchmark.run_plan import load_run_plan

BUNDLE_REVISION = "rev11-qualification-lock-bundle-v1"
CONTROL_DIR_NAME = "qualification-control"
FILES = {
    "package-lock.json": "package-lock.json",
    "engine/uv.lock": "uv.lock",
    "SOURCE_SHA256SUMS.txt": "SOURCE_SHA256SUMS.txt",
}


class LockBundleError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _regular(path: Path, *, label: str) -> Path:
    if path.is_symlink() or not path.is_file() or path.stat().st_size <= 0:
        raise LockBundleError(f"{label} must be a non-empty regular file: {path}")
    return path


def _workspace(path: Path) -> Path:
    resolved = path.resolve()
    if resolved.is_symlink() or not resolved.is_dir():
        raise LockBundleError("qualification workspace must be a real directory")
    return resolved


def _source_sha(value: str) -> str:
    if not re.fullmatch(r"[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?", value):
        raise LockBundleError("source SHA must be a 40- or 64-hex commit identity")
    return value.lower()


def _load_session(control: Path) -> dict:
    session_path = _regular(control / "qualification-session.json", label="qualification session")
    try:
        session = json.loads(session_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LockBundleError(f"cannot read qualification session: {exc}") from exc
    if not isinstance(session, dict) or session.get("schemaVersion") != 1 or session.get("revision") != BUNDLE_REVISION:
        raise LockBundleError("qualification session schema/revision is unsupported")
    return session


def seal(*, repo_root: Path, workspace: Path, source_sha: str, lock_report: Path | None, replace: bool) -> dict:
    root = repo_root.resolve()
    ws = _workspace(workspace)
    run_plan = load_run_plan(_regular(ws / "benchmark-run-plan.json", label="prepared run plan"), require_ready=True)
    locks = dependency_lock_pins(root)
    if run_plan.get("dependencyLocks") != locks:
        raise LockBundleError("prepared run plan does not match current generated dependency locks")

    control = ws / CONTROL_DIR_NAME
    if control.exists() and not replace:
        raise LockBundleError("qualification-control already exists; use --replace only after reviewing it")
    staging = Path(tempfile.mkdtemp(prefix=".qualification-control-", dir=ws))
    try:
        files: dict[str, str] = {}
        for relative, bundled_name in FILES.items():
            source = _regular(root / relative, label=relative)
            destination = staging / bundled_name
            shutil.copyfile(source, destination, follow_symlinks=False)
            files[bundled_name] = sha256_file(destination)
        if lock_report is not None:
            source = _regular(lock_report.resolve(), label="dependency lock report")
            destination = staging / "dependency-lock-report.json"
            shutil.copyfile(source, destination, follow_symlinks=False)
            files[destination.name] = sha256_file(destination)
        session = {
            "schemaVersion": 1,
            "revision": BUNDLE_REVISION,
            "sealedAtUtc": _utc_now(),
            "sourceHeadSha": _source_sha(source_sha),
            "runPlanSha256": run_plan["runPlanSha256"],
            "dependencyLocks": locks,
            "files": files,
        }
        (staging / "qualification-session.json").write_text(json.dumps(session, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        backup = ws / ".qualification-control-backup"
        if backup.exists():
            raise LockBundleError("stale qualification-control backup exists")
        if control.exists():
            control.replace(backup)
        try:
            staging.replace(control)
        except Exception:
            if backup.exists():
                backup.replace(control)
            raise
        shutil.rmtree(backup, ignore_errors=True)
        return session
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def restore(*, repo_root: Path, workspace: Path, expected_source_sha: str) -> dict:
    root = repo_root.resolve()
    ws = _workspace(workspace)
    control = ws / CONTROL_DIR_NAME
    if control.is_symlink() or not control.is_dir():
        raise LockBundleError("prepared workspace has no real qualification-control directory")
    session = _load_session(control)
    if session.get("sourceHeadSha") != _source_sha(expected_source_sha):
        raise LockBundleError("prepared qualification belongs to a different source commit")
    run_plan = load_run_plan(_regular(ws / "benchmark-run-plan.json", label="prepared run plan"), require_ready=True)
    if session.get("runPlanSha256") != run_plan.get("runPlanSha256") or session.get("dependencyLocks") != run_plan.get("dependencyLocks"):
        raise LockBundleError("qualification session does not match the prepared run plan")
    files = session.get("files")
    if not isinstance(files, dict):
        raise LockBundleError("qualification session files map is missing")
    for bundled_name in FILES.values():
        source = _regular(control / bundled_name, label=f"bundled {bundled_name}")
        if files.get(bundled_name) != sha256_file(source):
            raise LockBundleError(f"bundled lock/control file digest mismatch: {bundled_name}")
    for relative, bundled_name in FILES.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.with_suffix(destination.suffix + ".qualification.tmp")
        shutil.copyfile(control / bundled_name, temp, follow_symlinks=False)
        temp.replace(destination)
    locks = dependency_lock_pins(root)
    if locks != session.get("dependencyLocks"):
        raise LockBundleError("restored dependency lock bytes do not match the prepared session")
    return session


def main() -> int:
    parser = argparse.ArgumentParser(description="Seal or restore the exact registry-generated dependency locks bound to a prepared qualification run plan.")
    sub = parser.add_subparsers(dest="command", required=True)
    seal_parser = sub.add_parser("seal")
    seal_parser.add_argument("--repo-root", type=Path, default=ENGINE_ROOT.parent)
    seal_parser.add_argument("--workspace", required=True, type=Path)
    seal_parser.add_argument("--source-sha", required=True)
    seal_parser.add_argument("--lock-report", type=Path)
    seal_parser.add_argument("--replace", action="store_true")
    restore_parser = sub.add_parser("restore")
    restore_parser.add_argument("--repo-root", type=Path, default=ENGINE_ROOT.parent)
    restore_parser.add_argument("--workspace", required=True, type=Path)
    restore_parser.add_argument("--expected-source-sha", required=True)
    args = parser.parse_args()
    if args.command == "seal":
        payload = seal(repo_root=args.repo_root, workspace=args.workspace, source_sha=args.source_sha, lock_report=args.lock_report, replace=args.replace)
    else:
        payload = restore(repo_root=args.repo_root, workspace=args.workspace, expected_source_sha=args.expected_source_sha)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LockBundleError, ValueError, OSError) as exc:
        raise SystemExit(f"qualification lock bundle failed closed: {exc}")
