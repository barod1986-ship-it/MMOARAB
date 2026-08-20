from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.common import sha256_file
from mte_engine.benchmark.dependency_locks import dependency_lock_pins
from mte_engine.benchmark.freeze import load_freeze
from mte_engine.benchmark.run_plan import load_run_plan
from mte_engine.benchmark.source_binding import validate_source_binding

REVISION = "rev16-qualification-release-evidence-v1"


class ExportError(ValueError):
    pass


def _regular(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file() or path.stat().st_size <= 0:
        raise ExportError(f"{label} must be a non-empty regular file: {path}")
    return path


def _load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(_regular(path, label).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExportError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ExportError(f"{label} must contain a JSON object")
    return value


def export_release_evidence(*, repo_root: Path, workspace: Path, output_dir: Path, replace: bool) -> dict:
    root = repo_root.resolve()
    ws = workspace.resolve()
    if ws.is_symlink() or not ws.is_dir():
        raise ExportError("qualification workspace must be a real directory")
    control = ws / "qualification-control"
    if control.is_symlink() or not control.is_dir():
        raise ExportError("qualification workspace has no sealed qualification-control directory")

    session = _load_json(control / "qualification-session.json", "qualification session")
    run_plan = load_run_plan(_regular(ws / "benchmark-run-plan.json", "benchmark run plan"), require_ready=True)
    summary = _load_json(ws / "qualification-execution-summary.json", "qualification execution summary")
    freeze_path = _regular(ws / "production-profile-freeze.json", "production profile freeze")
    freeze = load_freeze(freeze_path)
    if freeze is None:
        raise ExportError("production profile freeze is invalid")
    if summary.get("gatePassed") is not True:
        raise ExportError("qualification execution did not pass the production gate")
    if session.get("runPlanSha256") != run_plan.get("runPlanSha256") or summary.get("runPlanSha256") != run_plan.get("runPlanSha256"):
        raise ExportError("qualification session/execution run-plan identities differ")
    if freeze.get("runPlanSha256") != run_plan.get("runPlanSha256"):
        raise ExportError("production freeze is not bound to the prepared run plan")
    if freeze.get("dependencyLocks") != dependency_lock_pins(root):
        raise ExportError("production freeze dependency locks differ from the restored repository locks")
    source_binding = validate_source_binding(freeze.get("qualifiedSource"))
    if source_binding.get("sourceHeadSha") != session.get("sourceHeadSha") or summary.get("qualifiedSourceHeadSha") != session.get("sourceHeadSha"):
        raise ExportError("qualified source identity differs across freeze/session/execution summary")

    files = {
        "package-lock.json": root / "package-lock.json",
        "uv.lock": root / "engine" / "uv.lock",
        "production-profile-freeze.json": freeze_path,
        "qualification-execution-summary.json": ws / "qualification-execution-summary.json",
        "qualification-session.json": control / "qualification-session.json",
    }
    for name, path in files.items():
        _regular(path, name)

    out = output_dir.resolve()
    if out.exists() and any(out.iterdir()) and not replace:
        raise ExportError(f"release-evidence output already contains files: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{out.name}.staging-", dir=out.parent))
    try:
        hashes: dict[str, str] = {}
        for name, source in files.items():
            target = staging / name
            shutil.copyfile(source, target, follow_symlinks=False)
            hashes[name] = sha256_file(target)
        manifest = {
            "schemaVersion": 1,
            "revision": REVISION,
            "qualifiedSourceHeadSha": session["sourceHeadSha"],
            "runPlanSha256": run_plan["runPlanSha256"],
            "freezeSha256": freeze["freezeSha256"],
            "dependencyLocks": freeze["dependencyLocks"],
            "qualifiedSource": source_binding,
            "files": hashes,
            "containsModelBytes": False,
            "containsCorpusBytes": False,
            "containsOcrTextTrace": False,
        }
        (staging / "qualification-release-evidence.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if out.exists():
            shutil.rmtree(out)
        staging.replace(out)
        return manifest
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export only release-safe evidence from a passing protected production qualification workspace.")
    parser.add_argument("--repo-root", type=Path, default=ENGINE_ROOT.parent)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    payload = export_release_evidence(repo_root=args.repo_root, workspace=args.workspace, output_dir=args.output_dir, replace=args.replace)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ExportError, ValueError, OSError) as exc:
        raise SystemExit(f"qualification release-evidence export failed closed: {exc}")
