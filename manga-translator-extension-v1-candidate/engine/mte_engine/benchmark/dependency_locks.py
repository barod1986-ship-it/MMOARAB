from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

from .common import is_sha256, require_dict, sha256_file

LOCK_PIN_REVISION = "rev11-qualification-dependency-lock-pins-v1"


class DependencyLockError(ValueError):
    pass


def _regular_file(path: Path, *, label: str) -> Path:
    if path.is_symlink() or not path.is_file() or path.stat().st_size <= 0:
        raise DependencyLockError(f"{label} must be a non-empty regular file")
    return path


def _dependency_name(spec: str) -> str | None:
    value = spec.strip()
    if not value or value.startswith(("-", ".")):
        return None
    match = re.match(r"^([A-Za-z0-9_.-]+)", value)
    return match.group(1).lower().replace("_", "-") if match else None


def _exact_pin(spec: str) -> tuple[str, str] | None:
    match = re.match(r"^([A-Za-z0-9_.-]+)==([^;\s]+)", spec.strip())
    if not match:
        return None
    return match.group(1).lower().replace("_", "-"), match.group(2)


def validate_package_lock(repo_root: Path) -> dict[str, Any]:
    package_path = _regular_file(repo_root / "package.json", label="package.json")
    lock_path = _regular_file(repo_root / "package-lock.json", label="package-lock.json")
    try:
        package = require_dict(json.loads(package_path.read_text(encoding="utf-8")), label="package.json")
        lock = require_dict(json.loads(lock_path.read_text(encoding="utf-8")), label="package-lock.json")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise DependencyLockError(f"cannot parse npm dependency graph: {exc}") from exc
    if lock.get("lockfileVersion") != 3:
        raise DependencyLockError("package-lock.json must use npm lockfileVersion 3")
    if lock.get("name") != package.get("name") or lock.get("version") != package.get("version"):
        raise DependencyLockError("package-lock.json root name/version do not match package.json")
    packages = lock.get("packages")
    if not isinstance(packages, dict) or len(packages) < 2 or not isinstance(packages.get(""), dict):
        raise DependencyLockError("package-lock.json does not contain a resolved package graph")
    root_entry = packages[""]
    for key in ("dependencies", "devDependencies"):
        expected = package.get(key, {})
        actual = root_entry.get(key, {})
        if actual != expected:
            raise DependencyLockError(f"package-lock.json root {key} do not exactly match package.json")
        if not isinstance(expected, dict):
            continue
        for name, requested in expected.items():
            entry = packages.get(f"node_modules/{name}")
            if not isinstance(entry, dict):
                raise DependencyLockError(f"package-lock.json is missing direct dependency {name}")
            if isinstance(requested, str) and re.fullmatch(r"\d+\.\d+\.\d+(?:[-+].+)?", requested):
                if entry.get("version") != requested:
                    raise DependencyLockError(f"package-lock.json resolved {name} to the wrong exact version")
            if entry.get("link") is not True and not isinstance(entry.get("integrity"), str):
                raise DependencyLockError(f"package-lock.json direct dependency has no integrity digest: {name}")
    return {"lockfileVersion": 3, "packageCount": len(packages), "sha256": sha256_file(lock_path)}


def validate_uv_lock(repo_root: Path) -> dict[str, Any]:
    pyproject_path = _regular_file(repo_root / "engine" / "pyproject.toml", label="engine/pyproject.toml")
    lock_path = _regular_file(repo_root / "engine" / "uv.lock", label="engine/uv.lock")
    try:
        pyproject = require_dict(tomllib.loads(pyproject_path.read_text(encoding="utf-8")), label="engine/pyproject.toml")
        lock = require_dict(tomllib.loads(lock_path.read_text(encoding="utf-8")), label="engine/uv.lock")
    except (OSError, tomllib.TOMLDecodeError, ValueError) as exc:
        raise DependencyLockError(f"cannot parse uv dependency graph: {exc}") from exc
    if lock.get("version") != 1:
        raise DependencyLockError("engine/uv.lock must use uv lock format version 1")
    packages = lock.get("package")
    if not isinstance(packages, list) or len(packages) < 2:
        raise DependencyLockError("engine/uv.lock does not contain a resolved package graph")
    by_name: dict[str, list[dict[str, Any]]] = {}
    for item in packages:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            by_name.setdefault(item["name"].lower().replace("_", "-"), []).append(item)
    project = require_dict(pyproject.get("project"), label="engine project")
    project_name = str(project.get("name", "")).lower().replace("_", "-")
    project_version = project.get("version")
    if not any(item.get("version") == project_version and isinstance(item.get("source"), dict) for item in by_name.get(project_name, [])):
        raise DependencyLockError("engine/uv.lock does not contain the current Engine project")
    specs: list[str] = [x for x in (project.get("dependencies") or []) if isinstance(x, str)]
    optional = project.get("optional-dependencies") or {}
    if isinstance(optional, dict):
        for values in optional.values():
            if isinstance(values, list):
                specs.extend(x for x in values if isinstance(x, str))
    for spec in specs:
        name = _dependency_name(spec)
        if name and name not in by_name:
            raise DependencyLockError(f"engine/uv.lock is missing direct dependency {name}")
        pin = _exact_pin(spec)
        if pin and not any(item.get("version") == pin[1] for item in by_name.get(pin[0], [])):
            raise DependencyLockError(f"engine/uv.lock does not resolve exact pin {pin[0]}=={pin[1]}")
    return {"lockVersion": 1, "packageCount": len(packages), "sha256": sha256_file(lock_path)}


def dependency_lock_pins(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    npm = validate_package_lock(root)
    uv = validate_uv_lock(root)
    return {
        "revision": LOCK_PIN_REVISION,
        "packageLockSha256": npm["sha256"],
        "uvLockSha256": uv["sha256"],
        "npmPackageCount": npm["packageCount"],
        "uvPackageCount": uv["packageCount"],
    }


def validate_dependency_lock_pins(value: object) -> dict[str, Any]:
    pins = require_dict(value, label="dependencyLocks")
    if pins.get("revision") != LOCK_PIN_REVISION:
        raise DependencyLockError("dependency lock pin revision is unsupported")
    for key in ("packageLockSha256", "uvLockSha256"):
        if not is_sha256(pins.get(key)):
            raise DependencyLockError(f"dependencyLocks.{key} is malformed")
    for key in ("npmPackageCount", "uvPackageCount"):
        count = pins.get(key)
        if isinstance(count, bool) or not isinstance(count, int) or count < 2:
            raise DependencyLockError(f"dependencyLocks.{key} must prove a non-trivial resolved graph")
    return pins
