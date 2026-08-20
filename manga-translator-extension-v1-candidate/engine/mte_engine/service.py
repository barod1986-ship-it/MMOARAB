from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from contextlib import suppress

from .config import EngineSettings
from .db import JobRepository
from .errors import EngineApiError
from .processor import process_staged_job
from .spool import SpoolStore
from .profile import ready_profile_fingerprints


class EngineWorker:
    def __init__(self, jobs: JobRepository, spool: SpoolStore, settings: EngineSettings) -> None:
        self._jobs = jobs
        self._spool = spool
        self._settings = settings
        self._wake = asyncio.Event()
        self._stopping = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._jobs.recover_after_startup(ready_profile_fingerprints(self._settings))
        self._task = asyncio.create_task(self._run(), name="mte-engine-worker")
        self.wake()

    async def stop(self) -> None:
        self._stopping = True
        self._wake.set()
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    def wake(self) -> None:
        self._wake.set()

    async def _run(self) -> None:
        while not self._stopping:
            queued = self._jobs.list_queued(limit=1)
            if not queued:
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=5.0)
                except TimeoutError:
                    pass
                continue
            await self._run_one(str(queued[0]["ticket"]))

    async def _run_one(self, ticket: str) -> None:
        row = self._jobs.claim(ticket)
        if not row:
            return
        if self._jobs.is_cancel_requested(ticket):
            self._jobs.mark_cancelled(ticket)
            return
        source_path = row.get("source_path")
        if not isinstance(source_path, str):
            self._jobs.fail(ticket, "invalid_source", "Queued job is missing its source spool artifact.")
            return
        try:
            spec = json.loads(str(row["processing_spec_json"]))
            profile_id = str(spec["profileId"])
            def progress(stage: str, completed: int, total: int) -> None:
                self._jobs.set_stage(ticket, stage, completed, total)
                if self._jobs.is_cancel_requested(ticket):
                    raise EngineApiError("job_cancelled", "Job was cancelled.", 409)
            self._spool.clear_result_candidates(ticket)
            result_path, artifact = await asyncio.to_thread(
                process_staged_job,
                Path(source_path),
                self._spool,
                self._settings,
                ticket=ticket,
                job_id=str(row["job_id"]),
                profile_id=profile_id,
                profile_fingerprint=str(row["profile_fingerprint"]),
                source_language=str(spec["sourceLanguage"]),
                target_language=str(spec["targetLanguage"]),
                stage_callback=progress,
                started_at=time.monotonic(),
            )
            if self._jobs.is_cancel_requested(ticket):
                self._spool.safe_unlink(str(result_path))
                self._jobs.mark_cancelled(ticket)
                return
            self._jobs.succeed(
                ticket,
                result_path=result_path,
                result_mime=artifact.mime,
                result_bytes=len(artifact.encoded),
                result_sha256=artifact.sha256,
                width=artifact.width,
                height=artifact.height,
                manifest=artifact.manifest,
            )
        except EngineApiError as exc:
            if exc.code == "job_cancelled":
                self._jobs.mark_cancelled(ticket)
            else:
                self._jobs.fail(ticket, exc.code, exc.message, retryable=exc.retryable)
        except Exception:
            self._jobs.fail(ticket, "internal_error", "Unexpected engine processing failure.")
