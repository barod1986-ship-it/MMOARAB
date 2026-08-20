from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .common import is_sha256

SOURCE_BINDING_REVISION = "rev16-qualified-runtime-source-binding-v1"
RUNTIME_TREES = ("src", "engine/mte_engine")
EXCLUDED_RELATIVE = {"engine/mte_engine/benchmark/production-profile-freeze.json"}
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$", re.I)


class SourceBindingError(ValueError):
    pass


def normalize_source_head_sha(value: str) -> str:
    if not isinstance(value, str) or not _SOURCE_SHA_RE.fullmatch(value.strip()):
        raise SourceBindingError("qualified source head must be a 40- or 64-hex commit identity")
    return value.strip().lower()


def _tree_digest(repo_root: Path, relative_root: str) -> dict[str, Any]:
    root = repo_root.resolve()
    base = (root / relative_root).resolve()
    try:
        base.relative_to(root)
    except ValueError as exc:
        raise SourceBindingError(f"runtime tree escapes repository: {relative_root}") from exc
    if base.is_symlink() or not base.is_dir():
        raise SourceBindingError(f"runtime tree is missing or unsafe: {relative_root}")

    files: list[Path] = []
    for path in base.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root).as_posix()
        if "__pycache__" in path.parts or rel in EXCLUDED_RELATIVE:
            continue
        files.append(path)
    files.sort(key=lambda p: p.relative_to(root).as_posix())
    if not files:
        raise SourceBindingError(f"runtime tree contains no files: {relative_root}")

    h = hashlib.sha256()
    for path in files:
        rel = path.relative_to(root).as_posix().encode("utf-8")
        digest = hashlib.sha256(path.read_bytes()).digest()
        h.update(rel)
        h.update(b"\0")
        h.update(digest)
    return {"fileCount": len(files), "treeSha256": "sha256:" + h.hexdigest()}


def qualified_source_binding(repo_root: Path, *, source_head_sha: str) -> dict[str, Any]:
    root = repo_root.resolve()
    return {
        "revision": SOURCE_BINDING_REVISION,
        "sourceHeadSha": normalize_source_head_sha(source_head_sha),
        "runtimeTrees": {relative: _tree_digest(root, relative) for relative in RUNTIME_TREES},
    }


def validate_source_binding(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("revision") != SOURCE_BINDING_REVISION:
        raise SourceBindingError("qualified source binding revision is unsupported")
    normalize_source_head_sha(value.get("sourceHeadSha", ""))
    trees = value.get("runtimeTrees")
    if not isinstance(trees, dict) or set(trees) != set(RUNTIME_TREES):
        raise SourceBindingError("qualified source binding runtime tree set is incomplete")
    for relative in RUNTIME_TREES:
        item = trees.get(relative)
        if not isinstance(item, dict):
            raise SourceBindingError(f"qualified source tree entry is malformed: {relative}")
        count = item.get("fileCount")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise SourceBindingError(f"qualified source tree file count is invalid: {relative}")
        if not is_sha256(item.get("treeSha256")):
            raise SourceBindingError(f"qualified source tree digest is invalid: {relative}")
    return value


def verify_current_source_binding(repo_root: Path, value: object) -> dict[str, Any]:
    binding = validate_source_binding(value)
    current = qualified_source_binding(repo_root, source_head_sha=binding["sourceHeadSha"])
    if current["runtimeTrees"] != binding["runtimeTrees"]:
        raise SourceBindingError("current runtime source trees differ from the source qualified by the production freeze")
    return binding
