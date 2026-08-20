from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from fastapi import Request

from .constants import MAX_SOURCE_BYTES
from .errors import EngineApiError


class SpoolStore:
    def __init__(self, data_dir: Path) -> None:
        self.root = data_dir / "spool"
        self.sources = self.root / "sources"
        self.results = self.root / "results"
        self.sources.mkdir(parents=True, exist_ok=True)
        self.results.mkdir(parents=True, exist_ok=True)
        for directory in (self.root, self.sources, self.results):
            try:
                os.chmod(directory, 0o700)
            except OSError:
                pass

    async def ingest_source(self, request: Request, *, ticket: str, expected_bytes: int, expected_sha256: str) -> Path:
        if expected_bytes > MAX_SOURCE_BYTES:
            raise EngineApiError("source_too_large", "Source exceeds the V1 32 MiB limit.", 413)
        fd, temp_name = tempfile.mkstemp(prefix=".source-", suffix=".tmp", dir=self.sources)
        total = 0
        digest = hashlib.sha256()
        try:
            with os.fdopen(fd, "wb") as handle:
                async for chunk in request.stream():
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_SOURCE_BYTES or total > expected_bytes:
                        raise EngineApiError("source_too_large", "Source upload exceeded the declared or protocol byte limit.", 413)
                    digest.update(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            if total != expected_bytes:
                raise EngineApiError("invalid_source", "Source byte count does not match job metadata.", 400)
            actual = "sha256:" + digest.hexdigest()
            if actual != expected_sha256:
                raise EngineApiError("source_hash_mismatch", "Source SHA-256 does not match job metadata.", 400)
            final_path = self.sources / f"{ticket}.bin"
            os.replace(temp_name, final_path)
            return final_path
        except Exception:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
            raise

    @staticmethod
    def verify_file(path: Path, *, expected_bytes: int, expected_sha256: str) -> bool:
        try:
            if not path.is_file() or path.stat().st_size != expected_bytes:
                return False
            digest = hashlib.sha256()
            total = 0
            with path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_SOURCE_BYTES or total > expected_bytes:
                        return False
                    digest.update(chunk)
            return total == expected_bytes and "sha256:" + digest.hexdigest() == expected_sha256
        except OSError:
            return False


    def cleanup_temp_files(self, cutoff_epoch: float) -> int:
        removed = 0
        for directory in (self.sources, self.results):
            for candidate in directory.iterdir():
                if not candidate.is_file():
                    continue
                is_temp = candidate.name.startswith(".source-") or candidate.name.endswith(".tmp")
                if not is_temp:
                    continue
                try:
                    if candidate.stat().st_mtime < cutoff_epoch:
                        candidate.unlink(missing_ok=True)
                        removed += 1
                except OSError:
                    continue
        return removed

    def allocate_result_path(self, ticket: str, suffix: str) -> Path:
        return self.results / f"{ticket}{suffix}"

    def clear_result_candidates(self, ticket: str) -> None:
        for suffix in (".webp", ".png", ".webp.tmp", ".png.tmp"):
            self.safe_unlink(str(self.results / f"{ticket}{suffix}"))

    @staticmethod
    def safe_unlink(path_value: str | None) -> None:
        if not path_value:
            return
        try:
            Path(path_value).unlink(missing_ok=True)
        except OSError:
            pass
