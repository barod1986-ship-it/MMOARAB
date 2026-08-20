from __future__ import annotations

import json
from pathlib import Path

import pytest

from mte_engine.benchmark.dependency_locks import DependencyLockError, dependency_lock_pins
from mte_engine.benchmark.run_plan import run_plan_digest
from scripts.manage_qualification_lock_bundle import restore, seal


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "engine").mkdir(parents=True)
    (root / "package.json").write_text(
        json.dumps({"name": "app", "version": "1.0.0", "dependencies": {"dep": "1.2.3"}, "devDependencies": {}}),
        encoding="utf-8",
    )
    (root / "package-lock.json").write_text(
        json.dumps({
            "name": "app",
            "version": "1.0.0",
            "lockfileVersion": 3,
            "packages": {
                "": {"name": "app", "version": "1.0.0", "dependencies": {"dep": "1.2.3"}, "devDependencies": {}},
                "node_modules/dep": {"version": "1.2.3", "integrity": "sha512-test"},
            },
        }),
        encoding="utf-8",
    )
    (root / "engine" / "pyproject.toml").write_text(
        '[project]\nname="engine-app"\nversion="0.1.0"\ndependencies=["pydep==2.0.0"]\n\n[project.optional-dependencies]\ntest=[]\n',
        encoding="utf-8",
    )
    (root / "engine" / "uv.lock").write_text(
        'version = 1\n\n[[package]]\nname = "engine-app"\nversion = "0.1.0"\nsource = { virtual = "." }\n\n[[package]]\nname = "pydep"\nversion = "2.0.0"\nsource = { registry = "https://pypi.org/simple" }\n',
        encoding="utf-8",
    )
    (root / "SOURCE_SHA256SUMS.txt").write_text("test-control-manifest\n", encoding="utf-8")
    return root


def _run_plan(lock_pins: dict) -> dict:
    value = {
        "schemaVersion": 2,
        "runPlanRevision": "rev11-production-benchmark-run-plan-v3",
        "createdAtUtc": "2026-08-19T12:00:00Z",
        "ready": True,
        "reasons": [],
        "corpusId": "corpus",
        "corpusManifestSha256": "sha256:" + "1" * 64,
        "policyRevision": "policy",
        "policySha256": "sha256:" + "2" * 64,
        "catalogRevision": "catalog",
        "catalogSha256": "sha256:" + "3" * 64,
        "candidatePlanRevision": "plan",
        "candidatePlanSha256": "sha256:" + "4" * 64,
        "executor": {"revision": "rev10-production-benchmark-executor-v1", "sourceSha256": "sha256:" + "5" * 64},
        "dependencyLocks": lock_pins,
        "artifactPins": [],
        "artifactReceiptSha256s": {},
    }
    value["runPlanSha256"] = run_plan_digest(value)
    return value


def test_dependency_lock_pins_require_real_resolved_graphs(tmp_path: Path):
    root = _repo(tmp_path)
    pins = dependency_lock_pins(root)
    assert pins["npmPackageCount"] == 2
    assert pins["uvPackageCount"] == 2
    (root / "package-lock.json").write_text("{}", encoding="utf-8")
    with pytest.raises(DependencyLockError):
        dependency_lock_pins(root)


def test_prepared_qualification_lock_bundle_restores_exact_bytes(tmp_path: Path):
    root = _repo(tmp_path)
    original_package_lock = (root / "package-lock.json").read_bytes()
    original_uv_lock = (root / "engine" / "uv.lock").read_bytes()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    plan = _run_plan(dependency_lock_pins(root))
    (workspace / "benchmark-run-plan.json").write_text(json.dumps(plan), encoding="utf-8")

    session = seal(repo_root=root, workspace=workspace, source_sha="a" * 40, lock_report=None, replace=False)
    assert session["runPlanSha256"] == plan["runPlanSha256"]

    (root / "package-lock.json").write_text("tampered", encoding="utf-8")
    (root / "engine" / "uv.lock").write_text("tampered", encoding="utf-8")
    restored = restore(repo_root=root, workspace=workspace, expected_source_sha="a" * 40)
    assert restored["dependencyLocks"] == plan["dependencyLocks"]
    assert (root / "package-lock.json").read_bytes() == original_package_lock
    assert (root / "engine" / "uv.lock").read_bytes() == original_uv_lock
