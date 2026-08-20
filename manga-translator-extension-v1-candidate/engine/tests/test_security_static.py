from __future__ import annotations

from pathlib import Path


def test_no_unsafe_deserialization_or_dynamic_execution():
    root = Path(__file__).parents[1] / "mte_engine"
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
    forbidden = ["pickle.loads", "pickle.load(", "torch.load(", "eval(", "exec(", "subprocess.", "os.system(", "shell=True"]
    for token in forbidden:
        assert token not in text


def test_translation_job_path_has_no_url_fetch_client_dependency():
    root = Path(__file__).parents[1] / "mte_engine"
    # Phase 7 deliberately adds one network-capable module for trusted, catalog-pinned
    # model artifacts. Translation jobs and their service path must still be incapable
    # of fetching arbitrary URLs supplied by page/job input.
    excluded = {"model_install.py"}
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in root.rglob("*.py")
        if path.name not in excluded
    )
    for token in ["requests.get", "requests.post", "httpx.get", "httpx.post", "urllib.request", "aiohttp"]:
        assert token not in text


def test_only_model_installer_owns_network_download_client():
    root = Path(__file__).parents[1] / "mte_engine"
    owners = [path.relative_to(root).as_posix() for path in root.rglob("*.py") if "urllib.request" in path.read_text(encoding="utf-8")]
    assert owners == ["model_install.py"]
