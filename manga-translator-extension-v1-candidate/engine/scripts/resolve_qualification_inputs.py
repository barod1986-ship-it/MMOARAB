from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath


class InputPathError(ValueError):
    pass


def _relative(value: str, *, label: str) -> PurePosixPath:
    if not value or "\\" in value or "\n" in value or "\r" in value:
        raise InputPathError(f"{label} must be a non-empty relative POSIX path without control characters")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise InputPathError(f"{label} must remain below the configured qualification input root")
    return path


def _no_symlink_components(root: Path, target: Path) -> None:
    current = root
    for part in target.relative_to(root).parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise InputPathError(f"qualification input path contains a symlink component: {current}")


def _resolve(root: Path, value: str, *, label: str, kind: str, may_not_exist: bool = False) -> Path:
    relative = _relative(value, label=label)
    target = root.joinpath(*relative.parts)
    _no_symlink_components(root, target)
    resolved = target.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise InputPathError(f"{label} escapes the qualification input root") from exc
    if not may_not_exist or resolved.exists():
        if kind == "file" and (not resolved.is_file() or resolved.is_symlink()):
            raise InputPathError(f"{label} must be a regular file")
        if kind == "dir" and (not resolved.is_dir() or resolved.is_symlink()):
            raise InputPathError(f"{label} must be a directory")
    return resolved


def _disjoint(workspace: Path, values: dict[str, Path]) -> None:
    for key, other in values.items():
        if key == "MTE_Q_WORKSPACE":
            continue
        overlaps = False
        for left, right in ((other, workspace), (workspace, other)):
            try:
                left.relative_to(right)
                overlaps = True
            except ValueError:
                pass
        if overlaps:
            raise InputPathError(f"workspace must be disjoint from qualification input path: {key}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve self-hosted production qualification inputs below one operator-controlled root. "
            "Prepare and execute phases expose only the paths each phase is allowed to consume."
        )
    )
    parser.add_argument("--phase", choices=("prepare", "execute"), default="prepare")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--reviews-dir")
    parser.add_argument("--manual-artifacts-dir")
    parser.add_argument("--benchmark-review")
    parser.add_argument("--github-env", type=Path)
    args = parser.parse_args()

    root_arg = args.root
    if root_arg.is_symlink():
        raise SystemExit("qualification input root must be a real directory, not a symlink")
    root = root_arg.resolve(strict=True)
    if not root.is_dir():
        raise SystemExit("qualification input root must be a real directory, not a symlink")

    values: dict[str, Path] = {
        "MTE_Q_CORPUS": _resolve(root, args.corpus, label="corpus", kind="file"),
        "MTE_Q_WORKSPACE": _resolve(root, args.workspace, label="workspace", kind="dir", may_not_exist=args.phase == "prepare"),
    }
    if args.phase == "prepare":
        if not args.reviews_dir or not args.manual_artifacts_dir:
            raise InputPathError("prepare phase requires --reviews-dir and --manual-artifacts-dir")
        if args.benchmark_review:
            raise InputPathError("prepare phase must not consume a benchmark review; seal it only after the run plan exists")
        values["MTE_Q_REVIEWS"] = _resolve(root, args.reviews_dir, label="reviews-dir", kind="dir")
        values["MTE_Q_MANUAL"] = _resolve(root, args.manual_artifacts_dir, label="manual-artifacts-dir", kind="dir")
    else:
        if args.reviews_dir or args.manual_artifacts_dir:
            raise InputPathError("execute phase must reuse the prepared workspace and may not re-intake artifact review/manual inputs")
        if not args.benchmark_review:
            raise InputPathError("execute phase requires --benchmark-review")
        values["MTE_Q_BENCHMARK_REVIEW"] = _resolve(root, args.benchmark_review, label="benchmark-review", kind="file")

    _disjoint(values["MTE_Q_WORKSPACE"], values)
    if args.github_env:
        with args.github_env.open("a", encoding="utf-8") as handle:
            for key, value in values.items():
                handle.write(f"{key}={value}\n")
    print(json.dumps({key: str(value) for key, value in values.items()}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InputPathError as exc:
        raise SystemExit(str(exc))
