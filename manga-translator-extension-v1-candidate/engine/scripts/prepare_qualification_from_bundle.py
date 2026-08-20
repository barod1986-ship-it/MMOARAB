from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.qualification_bundle import QualificationBundleError, resolve_below, verify_qualification_input_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="One-command protected-runner entrypoint: verify the sealed REV13 input bundle, then prepare the immutable real qualification workspace.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--bundle", required=True, help="Sealed bundle path relative to --root.")
    parser.add_argument("--workspace", required=True, help="Output workspace path relative to --root.")
    parser.add_argument("--download-automated", action="store_true", help="Acquire all seven automated primary-source artifacts from the allowlisted network sources.")
    parser.add_argument("--acquired-dir", type=Path)
    parser.add_argument("--acquisition-records-dir", type=Path)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    if args.root.is_symlink():
        raise SystemExit("qualification input root must be a real directory, not a symlink")
    root = args.root.resolve(strict=True)
    bundle_path = resolve_below(root, args.bundle, label="qualification input bundle", kind="file")
    resolved = verify_qualification_input_bundle(root, bundle_path, verify_semantics=True)
    workspace = resolve_below(root, args.workspace, label="workspace", kind="dir", may_not_exist=True)
    for other in (bundle_path, resolved["corpus"], resolved["reviewsDir"], resolved["manualArtifactsDir"]):
        for left, right in ((workspace, other), (other, workspace)):
            try:
                left.relative_to(right)
            except ValueError:
                continue
            raise QualificationBundleError(f"workspace overlaps sealed input: {other}")

    cmd = [
        sys.executable,
        str(ENGINE_ROOT / "scripts" / "run_production_qualification.py"),
        "--workspace", str(workspace),
        "--corpus", str(resolved["corpus"]),
        "--artifact-reviews-dir", str(resolved["reviewsDir"]),
        "--manual-artifacts-dir", str(resolved["manualArtifactsDir"]),
        "--input-bundle-sha256", str(resolved["bundleSha256"]),
    ]
    if args.download_automated:
        cmd.append("--download-automated")
    else:
        if args.acquired_dir is None or args.acquisition_records_dir is None:
            raise QualificationBundleError("offline prepare requires --acquired-dir and --acquisition-records-dir")
        cmd.extend(["--acquired-dir", str(args.acquired_dir.resolve()), "--acquisition-records-dir", str(args.acquisition_records_dir.resolve())])
    if args.replace:
        cmd.append("--replace")
    completed = subprocess.run(cmd, cwd=ENGINE_ROOT.parent, check=False)
    return completed.returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except QualificationBundleError as exc:
        raise SystemExit(str(exc))
