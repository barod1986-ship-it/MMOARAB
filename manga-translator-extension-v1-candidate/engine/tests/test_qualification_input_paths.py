from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "resolve_qualification_inputs.py"


def _base(tmp_path: Path):
    root = tmp_path / "qualification-root"
    root.mkdir()
    (root / "corpus.json").write_text("{}", encoding="utf-8")
    (root / "reviews").mkdir()
    (root / "manual").mkdir()
    return root


def _run(root: Path, *extra: str):
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--root",
        str(root),
        "--corpus",
        "corpus.json",
        "--reviews-dir",
        "reviews",
        "--manual-artifacts-dir",
        "manual",
        "--workspace",
        "workspace",
        *extra,
    ]
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def test_qualification_paths_resolve_below_operator_root(tmp_path: Path):
    root = _base(tmp_path)
    result = _run(root)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert Path(payload["MTE_Q_CORPUS"]) == (root / "corpus.json").resolve()
    assert Path(payload["MTE_Q_REVIEWS"]) == (root / "reviews").resolve()
    assert Path(payload["MTE_Q_MANUAL"]) == (root / "manual").resolve()
    assert Path(payload["MTE_Q_WORKSPACE"]) == (root / "workspace").resolve()


def test_qualification_paths_reject_parent_escape(tmp_path: Path):
    root = _base(tmp_path)
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--root",
        str(root),
        "--corpus",
        "../outside.json",
        "--reviews-dir",
        "reviews",
        "--manual-artifacts-dir",
        "manual",
        "--workspace",
        "workspace",
    ]
    result = subprocess.run(cmd, text=True, capture_output=True, check=False)
    assert result.returncode != 0
    assert "remain below" in (result.stderr + result.stdout)


def test_qualification_paths_reject_symlink_component(tmp_path: Path):
    root = _base(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "corpus.json").write_text("{}", encoding="utf-8")
    try:
        (root / "linked").symlink_to(outside, target_is_directory=True)
    except OSError:
        return
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--root",
        str(root),
        "--corpus",
        "linked/corpus.json",
        "--reviews-dir",
        "reviews",
        "--manual-artifacts-dir",
        "manual",
        "--workspace",
        "workspace",
    ]
    result = subprocess.run(cmd, text=True, capture_output=True, check=False)
    assert result.returncode != 0
    assert "symlink component" in (result.stderr + result.stdout)


def test_qualification_paths_reject_symlink_root(tmp_path: Path):
    real_root = _base(tmp_path)
    alias = tmp_path / "qualification-root-link"
    try:
        alias.symlink_to(real_root, target_is_directory=True)
    except OSError:
        return
    result = _run(alias)
    assert result.returncode != 0
    assert "root must be a real directory" in (result.stderr + result.stdout)


def test_qualification_workspace_must_not_overlap_review_inputs(tmp_path: Path):
    root = _base(tmp_path)
    cmd = [
        sys.executable, str(SCRIPT), "--root", str(root),
        "--corpus", "corpus.json", "--reviews-dir", "reviews",
        "--manual-artifacts-dir", "manual", "--workspace", "reviews/output",
    ]
    result = subprocess.run(cmd, text=True, capture_output=True, check=False)
    assert result.returncode != 0
    assert "workspace must be disjoint" in (result.stderr + result.stdout)


def test_execute_phase_requires_only_prepared_workspace_and_benchmark_review(tmp_path: Path):
    root = _base(tmp_path)
    (root / "workspace").mkdir()
    (root / "benchmark-review.json").write_text("{}", encoding="utf-8")
    cmd = [
        sys.executable, str(SCRIPT), "--phase", "execute", "--root", str(root),
        "--corpus", "corpus.json", "--workspace", "workspace",
        "--benchmark-review", "benchmark-review.json",
    ]
    result = subprocess.run(cmd, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert set(payload) == {"MTE_Q_CORPUS", "MTE_Q_WORKSPACE", "MTE_Q_BENCHMARK_REVIEW"}


def test_execute_phase_refuses_reintake_inputs(tmp_path: Path):
    root = _base(tmp_path)
    (root / "workspace").mkdir()
    (root / "benchmark-review.json").write_text("{}", encoding="utf-8")
    cmd = [
        sys.executable, str(SCRIPT), "--phase", "execute", "--root", str(root),
        "--corpus", "corpus.json", "--workspace", "workspace",
        "--benchmark-review", "benchmark-review.json", "--reviews-dir", "reviews",
    ]
    result = subprocess.run(cmd, text=True, capture_output=True, check=False)
    assert result.returncode != 0
    assert "may not re-intake" in (result.stderr + result.stdout)
