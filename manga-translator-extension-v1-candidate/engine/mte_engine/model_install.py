from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import os
import re
import sqlite3
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .errors import EngineApiError

_SHA_RE = re.compile(r"^sha256:([a-f0-9]{64})$")
_ARTIFACT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+()\[\]-]{0,191}$")
_MAX_MODEL_BYTES = 16 * 1024 * 1024 * 1024
_CHUNK_BYTES = 1024 * 1024
_MAX_REDIRECTS = 3


@dataclass(frozen=True, slots=True)
class DistributionArtifact:
    artifact_id: str
    revision: str
    url: str
    bytes: int
    sha256: str
    expected_filename: str
    format: str
    license_spdx: str
    redistribution: str
    allowed_hosts: frozenset[str]

    @property
    def sha256_hex(self) -> str:
        match = _SHA_RE.fullmatch(self.sha256)
        assert match is not None
        return match.group(1)


class DistributionCatalog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.schema_version = 1
        self.catalog_revision = "unavailable"
        self.artifacts: dict[str, DistributionArtifact] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Model distribution catalog is unreadable: {exc}") from exc
        if not isinstance(raw, dict) or raw.get("schemaVersion") != 1:
            raise RuntimeError("Unsupported model distribution catalog schema.")
        revision = raw.get("catalogRevision")
        allowed_hosts = raw.get("allowedHosts")
        artifacts = raw.get("artifacts")
        if not isinstance(revision, str) or not revision or not isinstance(allowed_hosts, list) or not isinstance(artifacts, list):
            raise RuntimeError("Model distribution catalog is malformed.")
        normalized_hosts: set[str] = set()
        for host in allowed_hosts:
            if not isinstance(host, str) or not host or host.lower() != host or ":" in host or "/" in host:
                raise RuntimeError("Model catalog allowedHosts contains an invalid hostname.")
            if host == "localhost" or host.endswith(".local") or "." not in host:
                raise RuntimeError("Model catalog allowedHosts must contain public DNS hostnames only.")
            try:
                ipaddress.ip_address(host)
            except ValueError:
                pass
            else:
                raise RuntimeError("Model catalog allowedHosts must not contain IP literals.")
            normalized_hosts.add(host)
        parsed: dict[str, DistributionArtifact] = {}
        for item in artifacts:
            artifact = self._parse_artifact(item, frozenset(normalized_hosts))
            if artifact.artifact_id in parsed:
                raise RuntimeError(f"Duplicate model artifactId: {artifact.artifact_id}")
            parsed[artifact.artifact_id] = artifact
        self.catalog_revision = revision
        self.artifacts = parsed

    @staticmethod
    def _parse_artifact(value: object, allowed_hosts: frozenset[str]) -> DistributionArtifact:
        if not isinstance(value, dict):
            raise RuntimeError("Model catalog artifact must be an object.")
        required = {
            "artifactId", "revision", "url", "bytes", "sha256", "expectedFilename",
            "format", "licenseSpdx", "redistribution",
        }
        if set(value) != required:
            raise RuntimeError("Model catalog artifact fields do not match schema V1.")
        artifact_id = value["artifactId"]
        revision = value["revision"]
        url = value["url"]
        byte_count = value["bytes"]
        sha256 = value["sha256"]
        filename = value["expectedFilename"]
        fmt = value["format"]
        license_spdx = value["licenseSpdx"]
        redistribution = value["redistribution"]
        if not isinstance(artifact_id, str) or not _ARTIFACT_ID_RE.fullmatch(artifact_id):
            raise RuntimeError("Invalid model artifactId.")
        if not isinstance(revision, str) or not revision or len(revision) > 200:
            raise RuntimeError("Invalid model artifact revision.")
        if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count <= 0 or byte_count > _MAX_MODEL_BYTES:
            raise RuntimeError("Invalid model artifact size.")
        if not isinstance(sha256, str) or _SHA_RE.fullmatch(sha256) is None:
            raise RuntimeError("Invalid model artifact SHA-256 pin.")
        if not isinstance(filename, str) or not _FILENAME_RE.fullmatch(filename) or filename in {".", ".."}:
            raise RuntimeError("Invalid model artifact expectedFilename.")
        if fmt != "file":
            raise RuntimeError("Unsupported model artifact format. V1 installs exact file artifacts only.")
        if not isinstance(license_spdx, str) or not license_spdx or len(license_spdx) > 100:
            raise RuntimeError("Invalid model artifact licenseSpdx.")
        if redistribution not in {"approved", "download-only"}:
            raise RuntimeError("Model artifact redistribution status is not installable.")
        if not isinstance(url, str):
            raise RuntimeError("Invalid model artifact URL.")
        parsed = urllib.parse.urlsplit(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host or parsed.username or parsed.password or parsed.fragment:
            raise RuntimeError("Model artifact URL must be a credential-free HTTPS URL.")
        if parsed.port not in (None, 443) or host not in allowed_hosts:
            raise RuntimeError("Model artifact URL host is not allowlisted.")
        return DistributionArtifact(
            artifact_id=artifact_id, revision=revision, url=url, bytes=byte_count, sha256=sha256,
            expected_filename=filename, format=fmt, license_spdx=license_spdx,
            redistribution=redistribution, allowed_hosts=allowed_hosts,
        )

    def require(self, artifact_id: str) -> DistributionArtifact:
        artifact = self.artifacts.get(artifact_id)
        if artifact is None:
            raise EngineApiError("model_not_found", "Requested model is not present in the trusted release catalog.", 404)
        return artifact


class ModelInstallRepository:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=10.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS model_installs (
                  ticket TEXT PRIMARY KEY,
                  artifact_id TEXT NOT NULL UNIQUE,
                  state TEXT NOT NULL,
                  downloaded_bytes INTEGER NOT NULL DEFAULT 0,
                  total_bytes INTEGER NOT NULL,
                  cancel_requested INTEGER NOT NULL DEFAULT 0,
                  error_code TEXT,
                  error_message TEXT,
                  created_at REAL NOT NULL,
                  updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_model_installs_state ON model_installs(state, updated_at);
                """
            )

    def recover_after_startup(self) -> None:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE model_installs SET state='queued', cancel_requested=0, error_code=NULL, error_message=NULL, updated_at=? WHERE state='running'",
                (now,),
            )

    def create_or_resume(self, artifact_id: str, total_bytes: int) -> dict[str, Any]:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM model_installs WHERE artifact_id=?", (artifact_id,)).fetchone()
            if row:
                state = str(row["state"])
                if state in {"failed", "cancelled", "succeeded"}:
                    conn.execute(
                        "UPDATE model_installs SET state='queued', cancel_requested=0, error_code=NULL, error_message=NULL, total_bytes=?, updated_at=? WHERE artifact_id=?",
                        (total_bytes, now, artifact_id),
                    )
                conn.execute("COMMIT")
                return self.by_artifact(artifact_id)
            ticket = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO model_installs(ticket,artifact_id,state,total_bytes,created_at,updated_at) VALUES(?,?,'queued',?,?,?)",
                (ticket, artifact_id, total_bytes, now, now),
            )
            conn.execute("COMMIT")
        return self.get(ticket)

    def get(self, ticket: str) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM model_installs WHERE ticket=?", (ticket,)).fetchone()
        if not row:
            raise EngineApiError("model_install_not_found", "Unknown model-install ticket.", 404)
        return dict(row)

    def by_artifact(self, artifact_id: str) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM model_installs WHERE artifact_id=?", (artifact_id,)).fetchone()
        if not row:
            raise EngineApiError("model_install_not_found", "No model-install state exists for this artifact.", 404)
        return dict(row)

    def list_rows(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM model_installs ORDER BY created_at").fetchall()
        return [dict(row) for row in rows]

    def list_queued(self, limit: int = 1) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM model_installs WHERE state='queued' ORDER BY updated_at LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def claim(self, ticket: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("UPDATE model_installs SET state='running', updated_at=? WHERE ticket=? AND state='queued'", (time.time(), ticket))
            return cur.rowcount == 1

    def progress(self, ticket: str, downloaded: int) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE model_installs SET downloaded_bytes=?, updated_at=? WHERE ticket=? AND state='running'", (downloaded, time.time(), ticket))

    def cancel(self, ticket: str) -> dict[str, Any]:
        row = self.get(ticket)
        if row["state"] in {"succeeded", "failed", "cancelled"}:
            return row
        with self._lock, self._connect() as conn:
            if row["state"] == "queued":
                conn.execute("UPDATE model_installs SET state='cancelled', cancel_requested=1, updated_at=? WHERE ticket=?", (time.time(), ticket))
            else:
                conn.execute("UPDATE model_installs SET cancel_requested=1, updated_at=? WHERE ticket=?", (time.time(), ticket))
        return self.get(ticket)

    def cancel_requested(self, ticket: str) -> bool:
        return bool(self.get(ticket)["cancel_requested"])

    def succeed(self, ticket: str, downloaded: int) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE model_installs SET state='succeeded', downloaded_bytes=?, cancel_requested=0, error_code=NULL, error_message=NULL, updated_at=? WHERE ticket=?", (downloaded, time.time(), ticket))

    def mark_cancelled(self, ticket: str, downloaded: int) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE model_installs SET state='cancelled', downloaded_bytes=?, cancel_requested=1, updated_at=? WHERE ticket=?", (downloaded, time.time(), ticket))

    def fail(self, ticket: str, code: str, message: str, downloaded: int) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE model_installs SET state='failed', downloaded_bytes=?, error_code=?, error_message=?, updated_at=? WHERE ticket=?", (downloaded, code, message[:500], time.time(), ticket))


class _CatalogRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: frozenset[str]) -> None:
        super().__init__()
        self.allowed_hosts = allowed_hosts
        self.redirects = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        self.redirects += 1
        if self.redirects > _MAX_REDIRECTS:
            raise urllib.error.HTTPError(newurl, code, "Too many model download redirects", headers, fp)
        parsed = urllib.parse.urlsplit(newurl)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or parsed.port not in (None, 443) or host not in self.allowed_hosts or parsed.username or parsed.password or parsed.fragment:
            raise urllib.error.HTTPError(newurl, code, "Model redirect left trusted HTTPS host allowlist", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class ModelInstaller:
    def __init__(self, *, catalog: DistributionCatalog, model_dir: Path, data_dir: Path, repository: ModelInstallRepository) -> None:
        self.catalog = catalog
        self.model_dir = model_dir
        self.data_dir = data_dir
        self.repository = repository
        self.download_dir = data_dir / "model-downloads"
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        for path in (self.model_dir, self.download_dir):
            try:
                os.chmod(path, 0o700)
            except OSError:
                pass

    def final_path(self, artifact: DistributionArtifact) -> Path:
        target = (self.model_dir / artifact.expected_filename).resolve()
        base = self.model_dir.resolve()
        if target.parent != base:
            raise EngineApiError("model_catalog_invalid", "Model filename escapes the model directory.", 500)
        return target

    def partial_path(self, artifact: DistributionArtifact) -> Path:
        return self.download_dir / f"{artifact.artifact_id}.part"

    def installed(self, artifact: DistributionArtifact) -> bool:
        path = self.final_path(artifact)
        if not path.is_file() or path.is_symlink():
            return False
        try:
            if path.stat().st_size != artifact.bytes:
                return False
            return _hash_file(path) == artifact.sha256_hex
        except OSError:
            return False

    def install(self, artifact: DistributionArtifact, ticket: str, progress: Callable[[int], None], cancelled: Callable[[], bool]) -> Path:
        if self.installed(artifact):
            progress(artifact.bytes)
            return self.final_path(artifact)
        part = self.partial_path(artifact)
        final = self.final_path(artifact)
        if part.exists() and (not part.is_file() or part.is_symlink()):
            part.unlink(missing_ok=True)
        offset = part.stat().st_size if part.exists() else 0
        if offset > artifact.bytes:
            part.unlink(missing_ok=True)
            offset = 0
        progress(offset)
        if cancelled():
            raise _Cancelled(offset)
        try:
            offset = self._download(artifact, part, offset, progress, cancelled)
            if offset != artifact.bytes:
                raise EngineApiError("model_download_size_mismatch", "Downloaded model size does not match the catalog pin.", 502, retryable=True)
            digest = _hash_file(part)
            if digest != artifact.sha256_hex:
                part.unlink(missing_ok=True)
                raise EngineApiError("model_download_hash_mismatch", "Downloaded model SHA-256 does not match the trusted catalog.", 502, retryable=True)
            os.replace(part, final)
            try:
                os.chmod(final, 0o600)
            except OSError:
                pass
            return final
        except _Cancelled:
            raise
        except EngineApiError:
            raise
        except (OSError, urllib.error.URLError, urllib.error.HTTPError, ssl.SSLError) as exc:
            raise EngineApiError("model_download_failed", "Model download failed before integrity verification.", 502, retryable=True) from exc

    def _download(self, artifact: DistributionArtifact, part: Path, offset: int, progress: Callable[[int], None], cancelled: Callable[[], bool]) -> int:
        headers = {"Accept": "application/octet-stream", "User-Agent": "mte-local-engine/0.4"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        request = urllib.request.Request(artifact.url, headers=headers, method="GET")
        context = ssl.create_default_context()
        # HTTPS certificate validation is explicit, and redirect validation stays tied to
        # the immutable catalog host allowlist.
        opener = urllib.request.build_opener(
            _CatalogRedirectHandler(artifact.allowed_hosts),
            urllib.request.HTTPSHandler(context=context),
        )
        with opener.open(request, timeout=30) as response:
            status = int(getattr(response, "status", response.getcode()))
            if offset and status == 200:
                part.unlink(missing_ok=True)
                offset = 0
            elif offset and status == 206:
                content_range = response.headers.get("Content-Range", "")
                if not content_range.startswith(f"bytes {offset}-") or not content_range.endswith(f"/{artifact.bytes}"):
                    raise EngineApiError("model_download_resume_invalid", "Server returned an invalid Content-Range for model resume.", 502, retryable=True)
            elif status != 200:
                raise EngineApiError("model_download_failed", f"Model host returned HTTP {status}.", 502, retryable=True)
            declared = response.headers.get("Content-Length")
            if declared and declared.isdigit():
                expected_remaining = artifact.bytes - offset
                if int(declared) != expected_remaining:
                    raise EngineApiError("model_download_size_mismatch", "Model host Content-Length does not match the trusted catalog.", 502, retryable=True)
            mode = "ab" if offset else "wb"
            current = offset
            with part.open(mode) as handle:
                while True:
                    if cancelled():
                        handle.flush()
                        os.fsync(handle.fileno())
                        raise _Cancelled(current)
                    chunk = response.read(_CHUNK_BYTES)
                    if not chunk:
                        break
                    current += len(chunk)
                    if current > artifact.bytes:
                        raise EngineApiError("model_download_size_mismatch", "Model download exceeded the catalog byte limit.", 502, retryable=True)
                    handle.write(chunk)
                    progress(current)
                handle.flush()
                os.fsync(handle.fileno())
            return current


@dataclass(slots=True)
class _Cancelled(Exception):
    downloaded: int


class ModelDownloadWorker:
    def __init__(self, installer: ModelInstaller) -> None:
        self.installer = installer
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._stop = False

    async def start(self) -> None:
        self.installer.repository.recover_after_startup()
        self._stop = False
        self._task = asyncio.create_task(self._run(), name="mte-model-download-worker")
        self.wake()

    async def stop(self) -> None:
        self._stop = True
        self.wake()
        if self._task:
            await self._task
            self._task = None

    def wake(self) -> None:
        self._wake.set()

    async def _run(self) -> None:
        while not self._stop:
            queued = self.installer.repository.list_queued(limit=1)
            if not queued:
                self._wake.clear()
                await self._wake.wait()
                continue
            row = queued[0]
            ticket = str(row["ticket"])
            if not self.installer.repository.claim(ticket):
                continue
            artifact_id = str(row["artifact_id"])
            try:
                artifact = self.installer.catalog.require(artifact_id)
                path = await asyncio.to_thread(
                    self.installer.install,
                    artifact,
                    ticket,
                    lambda count: self.installer.repository.progress(ticket, count),
                    lambda: self.installer.repository.cancel_requested(ticket),
                )
                if not path.is_file():
                    raise EngineApiError("model_install_failed", "Verified model artifact was not atomically installed.", 500)
                self.installer.repository.succeed(ticket, artifact.bytes)
            except _Cancelled as exc:
                self.installer.repository.mark_cancelled(ticket, exc.downloaded)
            except EngineApiError as exc:
                artifact = self.installer.catalog.artifacts.get(artifact_id)
                part = self.installer.partial_path(artifact) if artifact is not None else None
                downloaded = part.stat().st_size if part is not None and part.is_file() and not part.is_symlink() else 0
                self.installer.repository.fail(ticket, exc.code, exc.message, downloaded)
            except Exception:
                self.installer.repository.fail(ticket, "model_install_failed", "Unexpected model installer failure.", 0)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_catalog_snapshot(catalog: DistributionCatalog, installer: ModelInstaller) -> dict[str, object]:
    rows = {str(row["artifact_id"]): row for row in installer.repository.list_rows()}
    artifacts: list[dict[str, object]] = []
    for artifact in catalog.artifacts.values():
        row = rows.get(artifact.artifact_id)
        installed = installer.installed(artifact)
        state = "ready" if installed else (str(row["state"]) if row else "missing")
        downloaded = artifact.bytes if installed else int(row["downloaded_bytes"] if row else 0)
        item: dict[str, object] = {
            "artifactId": artifact.artifact_id,
            "revision": artifact.revision,
            "expectedFilename": artifact.expected_filename,
            "bytes": artifact.bytes,
            "sha256": artifact.sha256,
            "licenseSpdx": artifact.license_spdx,
            "redistribution": artifact.redistribution,
            "state": state,
            "downloadedBytes": downloaded,
        }
        if row:
            item["ticket"] = str(row["ticket"])
            if row.get("error_code"):
                item["error"] = {"code": row["error_code"], "message": row.get("error_message") or row["error_code"]}
        artifacts.append(item)
    return {"schemaVersion": 1, "catalogRevision": catalog.catalog_revision, "artifacts": artifacts}


def model_install_status(row: dict[str, Any]) -> dict[str, object]:
    payload: dict[str, object] = {
        "ticket": str(row["ticket"]),
        "artifactId": str(row["artifact_id"]),
        "state": str(row["state"]),
        "downloadedBytes": int(row["downloaded_bytes"]),
        "totalBytes": int(row["total_bytes"]),
        "cancelRequested": bool(row["cancel_requested"]),
    }
    if row.get("error_code"):
        payload["error"] = {
            "code": str(row["error_code"]),
            "message": str(row.get("error_message") or row["error_code"]),
        }
    return payload
