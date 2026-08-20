from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from mte_engine.app import create_app
from mte_engine.config import EngineSettings, PairingStore
from mte_engine.model_install import DistributionCatalog, ModelInstallRepository, ModelInstaller

ORIGIN = "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def write_catalog(path: Path, *, url: str, payload: bytes, allowed_hosts: list[str] | None = None, fmt: str = "file") -> None:
    path.write_text(json.dumps({
        "schemaVersion": 1,
        "catalogRevision": "test-v1",
        "allowedHosts": allowed_hosts or ["models.example.test"],
        "artifacts": [{
            "artifactId": "ocr-test",
            "revision": "r1",
            "url": url,
            "bytes": len(payload),
            "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
            "expectedFilename": "ocr-test.bin",
            "format": fmt,
            "licenseSpdx": "Apache-2.0",
            "redistribution": "download-only",
        }],
    }), encoding="utf-8")


def test_catalog_rejects_untrusted_or_non_file_artifacts(tmp_path: Path):
    payload = b"model"
    cases = [
        ("http://models.example.test/model.bin", ["models.example.test"], "file"),
        ("https://user:pass@models.example.test/model.bin", ["models.example.test"], "file"),
        ("https://evil.example/model.bin", ["models.example.test"], "file"),
        ("https://models.example.test/model.bin", ["models.example.test"], "zip"),
        ("https://127.0.0.1/model.bin", ["127.0.0.1"], "file"),
        ("https://localhost/model.bin", ["localhost"], "file"),
    ]
    for index, (url, hosts, fmt) in enumerate(cases):
        path = tmp_path / f"catalog-{index}.json"
        write_catalog(path, url=url, payload=payload, allowed_hosts=hosts, fmt=fmt)
        with pytest.raises(RuntimeError):
            DistributionCatalog(path)


def test_repository_recovers_running_and_requeues_terminal_for_verified_reinstall(tmp_path: Path):
    repo = ModelInstallRepository(tmp_path / "installs.sqlite3")
    row = repo.create_or_resume("ocr-test", 100)
    assert repo.claim(str(row["ticket"]))
    repo.recover_after_startup()
    assert repo.get(str(row["ticket"]))["state"] == "queued"
    assert repo.claim(str(row["ticket"]))
    repo.succeed(str(row["ticket"]), 100)
    reset = repo.create_or_resume("ocr-test", 100)
    assert reset["state"] == "queued"


class FakeResponse(io.BytesIO):
    def __init__(self, payload: bytes, status: int = 200, headers: dict[str, str] | None = None):
        super().__init__(payload)
        self.status = status
        self.headers = headers or {"Content-Length": str(len(payload))}

    def getcode(self) -> int:
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


class FakeOpener:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.request_headers: dict[str, str] = {}

    def open(self, request, timeout: int = 30):  # type: ignore[no-untyped-def]
        self.request_headers = dict(request.header_items())
        return self.response


def test_exact_model_download_is_hash_verified_and_atomically_installed(monkeypatch, tmp_path: Path):
    payload = b"verified-model-bytes"
    catalog_path = tmp_path / "catalog.json"
    write_catalog(catalog_path, url="https://models.example.test/model.bin", payload=payload)
    catalog = DistributionCatalog(catalog_path)
    repo = ModelInstallRepository(tmp_path / "installs.sqlite3")
    installer = ModelInstaller(catalog=catalog, model_dir=tmp_path / "models", data_dir=tmp_path, repository=repo)
    opener = FakeOpener(FakeResponse(payload))
    monkeypatch.setattr("urllib.request.build_opener", lambda *args, **kwargs: opener)
    artifact = catalog.require("ocr-test")
    progress: list[int] = []
    result = installer.install(artifact, "ticket", progress.append, lambda: False)
    assert result.read_bytes() == payload
    assert installer.installed(artifact)
    assert not installer.partial_path(artifact).exists()
    assert progress[-1] == len(payload)


def test_hash_mismatch_removes_partial(monkeypatch, tmp_path: Path):
    expected = b"expected-model"
    actual = b"tampered-mode!"
    assert len(expected) == len(actual)
    catalog_path = tmp_path / "catalog.json"
    write_catalog(catalog_path, url="https://models.example.test/model.bin", payload=expected)
    catalog = DistributionCatalog(catalog_path)
    repo = ModelInstallRepository(tmp_path / "installs.sqlite3")
    installer = ModelInstaller(catalog=catalog, model_dir=tmp_path / "models", data_dir=tmp_path, repository=repo)
    monkeypatch.setattr("urllib.request.build_opener", lambda *args, **kwargs: FakeOpener(FakeResponse(actual)))
    artifact = catalog.require("ocr-test")
    with pytest.raises(Exception, match="SHA-256"):
        installer.install(artifact, "ticket", lambda _: None, lambda: False)
    assert not installer.partial_path(artifact).exists()
    assert not installer.final_path(artifact).exists()


def test_resume_uses_range_and_requires_exact_content_range(monkeypatch, tmp_path: Path):
    payload = b"0123456789abcdef"
    catalog_path = tmp_path / "catalog.json"
    write_catalog(catalog_path, url="https://models.example.test/model.bin", payload=payload)
    catalog = DistributionCatalog(catalog_path)
    repo = ModelInstallRepository(tmp_path / "installs.sqlite3")
    installer = ModelInstaller(catalog=catalog, model_dir=tmp_path / "models", data_dir=tmp_path, repository=repo)
    artifact = catalog.require("ocr-test")
    part = installer.partial_path(artifact)
    prefix = payload[:5]
    part.write_bytes(prefix)
    response = FakeResponse(payload[5:], status=206, headers={
        "Content-Length": str(len(payload) - 5),
        "Content-Range": f"bytes 5-{len(payload)-1}/{len(payload)}",
    })
    opener = FakeOpener(response)
    monkeypatch.setattr("urllib.request.build_opener", lambda *args, **kwargs: opener)
    result = installer.install(artifact, "ticket", lambda _: None, lambda: False)
    assert result.read_bytes() == payload
    assert opener.request_headers.get("Range") == "bytes=5-"


@pytest.mark.asyncio
async def test_setup_model_endpoints_are_authenticated_and_empty_catalog_is_fail_closed(tmp_path: Path):
    catalog_path = tmp_path / "distribution.json"
    catalog_path.write_text(json.dumps({
        "schemaVersion": 1,
        "catalogRevision": "unfrozen-test",
        "allowedHosts": [],
        "artifacts": [],
    }), encoding="utf-8")
    settings = EngineSettings(
        data_dir=tmp_path,
        port=17891,
        model_distribution_catalog_path=catalog_path,
        model_artifacts_dir=tmp_path / "models",
    )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 44221))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:17891") as http:
            pairing = PairingStore(tmp_path)
            assert (await http.get("/v1/setup/models", headers={"Origin": ORIGIN})).status_code == 401
            headers = {"Origin": ORIGIN, "Authorization": f"Bearer {pairing.token}"}
            caps = await http.get("/v1/capabilities", headers=headers)
            assert caps.status_code == 200
            catalog = await http.get("/v1/setup/models", headers=headers)
            assert catalog.status_code == 200
            assert catalog.json() == {"schemaVersion": 1, "catalogRevision": "unfrozen-test", "artifacts": []}
            missing = await http.post("/v1/setup/models/not-published/install", headers=headers)
            assert missing.status_code == 404
            assert missing.json()["error"]["code"] == "model_not_found"
