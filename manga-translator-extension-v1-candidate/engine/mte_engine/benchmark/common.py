from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

SHA256_PREFIX = "sha256:"


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return SHA256_PREFIX + hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return SHA256_PREFIX + digest.hexdigest()


def sha256_path(path: Path) -> str:
    """Hash a file or a directory tree deterministically.

    Directory digests include relative POSIX paths, file sizes, and file bytes in
    lexical order. Symlinks are refused so a model pin cannot silently escape the
    reviewed artifact directory.
    """
    if path.is_symlink():
        raise ValueError("Symlink model artifacts cannot be pinned")
    if path.is_file():
        return sha256_file(path)
    if not path.is_dir():
        raise FileNotFoundError(path)
    digest = hashlib.sha256()
    files = sorted(item for item in path.rglob("*") if item.is_file())
    if not files:
        raise ValueError("Model artifact directory is empty")
    for item in files:
        if item.is_symlink():
            raise ValueError("Symlink model artifacts cannot be pinned")
        relative = item.relative_to(path).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(item.stat().st_size.to_bytes(8, "big"))
        with item.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    return SHA256_PREFIX + digest.hexdigest()


def is_sha256(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith(SHA256_PREFIX) or len(value) != 71:
        return False
    try:
        int(value[len(SHA256_PREFIX):], 16)
    except ValueError:
        return False
    return True


def require_dict(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def require_list(value: object, *, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value



def reject_nonfinite_numbers(value: Any, *, label: str = "json") -> None:
    """Reject NaN/Infinity anywhere in externally supplied JSON-like data."""
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{label} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            reject_nonfinite_numbers(item, label=f"{label}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            reject_nonfinite_numbers(item, label=f"{label}.{key}")
        return
    raise ValueError(f"{label} contains a non-JSON value")

def finite_nonnegative(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{label} must be finite and non-negative")
    return number
