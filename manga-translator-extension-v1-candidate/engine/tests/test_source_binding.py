from __future__ import annotations

from pathlib import Path

import pytest

from mte_engine.benchmark.source_binding import (
    SourceBindingError,
    qualified_source_binding,
    validate_source_binding,
    verify_current_source_binding,
)


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.ts").write_text("export const a=1;\n", encoding="utf-8")
    (tmp_path / "engine" / "mte_engine" / "benchmark").mkdir(parents=True)
    (tmp_path / "engine" / "mte_engine" / "core.py").write_text("VALUE=1\n", encoding="utf-8")
    # Promotion of the freeze itself must not invalidate the source binding.
    (tmp_path / "engine" / "mte_engine" / "benchmark" / "production-profile-freeze.json").write_text("{}\n", encoding="utf-8")
    return tmp_path


def test_source_binding_ignores_promoted_freeze_but_detects_runtime_drift(tmp_path: Path):
    root = _repo(tmp_path)
    binding = qualified_source_binding(root, source_head_sha="a" * 40)
    assert validate_source_binding(binding) == binding
    (root / "engine" / "mte_engine" / "benchmark" / "production-profile-freeze.json").write_text('{"new":true}\n', encoding="utf-8")
    assert verify_current_source_binding(root, binding) == binding
    (root / "engine" / "mte_engine" / "core.py").write_text("VALUE=2\n", encoding="utf-8")
    with pytest.raises(SourceBindingError, match="differ"):
        verify_current_source_binding(root, binding)


def test_source_binding_detects_extension_runtime_drift(tmp_path: Path):
    root = _repo(tmp_path)
    binding = qualified_source_binding(root, source_head_sha="b" * 40)
    (root / "src" / "a.ts").write_text("export const a=2;\n", encoding="utf-8")
    with pytest.raises(SourceBindingError, match="differ"):
        verify_current_source_binding(root, binding)


def test_source_binding_rejects_untrusted_commit_identity(tmp_path: Path):
    root = _repo(tmp_path)
    with pytest.raises(SourceBindingError, match="commit identity"):
        qualified_source_binding(root, source_head_sha="main")
