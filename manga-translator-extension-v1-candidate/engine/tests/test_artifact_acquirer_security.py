from __future__ import annotations

import importlib.util
import socket
from pathlib import Path

import pytest

from mte_engine.benchmark.acquisition import AcquisitionError, validate_source_registry


def _module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "acquire_official_artifact.py"
    spec = importlib.util.spec_from_file_location("mte_acquire_official_artifact_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_downloader_redacts_redirect_query_and_fragment_from_provenance():
    module = _module()
    assert module._redacted_url("https://cdn.example.test/path/model.bin?X-Amz-Credential=secret#fragment") == "https://cdn.example.test/path/model.bin"


def test_downloader_refuses_private_dns_resolution(monkeypatch):
    module = _module()
    monkeypatch.setattr(module.socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(AcquisitionError, match="non-public address"):
        module._require_public_dns("models.example.test")


def test_automated_registry_rejects_signed_or_ephemeral_query_urls():
    registry = {
        "schemaVersion": 2,
        "registryRevision": "r",
        "artifacts": {"model": {
            "mode": "direct-https-file",
            "primaryDocumentation": "https://docs.example.test/model",
            "retrievalUrl": "https://downloads.example.test/model.bin?token=secret",
            "allowedHostSuffixes": ["example.test"],
            "expectedFilename": "model.bin",
            "upstreamRevision": "v1",
            "maxBytes": 1024,
        }},
    }
    with pytest.raises(AcquisitionError, match="query or fragment"):
        validate_source_registry(registry)
