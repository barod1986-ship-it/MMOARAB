from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.qualification_bundle import QualificationBundleError, resolve_below, verify_qualification_input_bundle


def _disjoint(workspace: Path, inputs: list[Path]) -> None:
    for other in inputs:
        for left, right in ((workspace, other), (other, workspace)):
            try:
                left.relative_to(right)
            except ValueError:
                continue
            raise QualificationBundleError(f"workspace must be disjoint from sealed qualification input path: {other}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-verify a sealed qualification input bundle and resolve prepare inputs below the operator-controlled root.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--bundle", required=True, help="Sealed bundle path relative to --root.")
    parser.add_argument("--workspace", required=True, help="Prepared workspace path relative to --root.")
    parser.add_argument("--github-env", type=Path)
    args = parser.parse_args()

    if args.root.is_symlink():
        raise SystemExit("qualification input root must be a real directory, not a symlink")
    root = args.root.resolve(strict=True)
    bundle_path = resolve_below(root, args.bundle, label="qualification input bundle", kind="file")
    result = verify_qualification_input_bundle(root, bundle_path, verify_semantics=True)
    workspace = resolve_below(root, args.workspace, label="workspace", kind="dir", may_not_exist=True)
    _disjoint(workspace, [bundle_path, result["corpus"], result["reviewsDir"], result["manualArtifactsDir"]])

    values = {
        "MTE_Q_INPUT_BUNDLE": str(bundle_path),
        "MTE_Q_INPUT_BUNDLE_SHA256": str(result["bundleSha256"]),
        "MTE_Q_CORPUS": str(result["corpus"]),
        "MTE_Q_REVIEWS": str(result["reviewsDir"]),
        "MTE_Q_MANUAL": str(result["manualArtifactsDir"]),
        "MTE_Q_WORKSPACE": str(workspace),
    }
    if args.github_env:
        with args.github_env.open("a", encoding="utf-8") as handle:
            for key, value in values.items():
                if "\n" in value or "\r" in value:
                    raise QualificationBundleError(f"unsafe newline in resolved environment value: {key}")
                handle.write(f"{key}={value}\n")
    print(json.dumps(values, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except QualificationBundleError as exc:
        raise SystemExit(str(exc))
