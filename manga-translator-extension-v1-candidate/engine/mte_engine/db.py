from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .errors import EngineApiError
from .models import CreateJobRequest

TERMINAL_STATES = {"succeeded", "failed", "cancelled", "interrupted"}


class JobRepository:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        for candidate in (self._db_path, Path(str(self._db_path) + "-wal"), Path(str(self._db_path) + "-shm")):
            try:
                if candidate.exists():
                    os.chmod(candidate, 0o600)
            except OSError:
                pass
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                  ticket TEXT PRIMARY KEY,
                  job_id TEXT NOT NULL,
                  idempotency_key TEXT NOT NULL,
                  request_fingerprint TEXT NOT NULL,
                  source_sha256 TEXT NOT NULL,
                  source_bytes INTEGER NOT NULL,
                  source_mime TEXT NOT NULL,
                  processing_spec_json TEXT NOT NULL,
                  profile_fingerprint TEXT NOT NULL,
                  state TEXT NOT NULL,
                  stage TEXT,
                  progress_completed INTEGER,
                  progress_total INTEGER,
                  source_path TEXT,
                  result_path TEXT,
                  result_mime TEXT,
                  result_bytes INTEGER,
                  result_sha256 TEXT,
                  result_manifest_json TEXT,
                  width INTEGER,
                  height INTEGER,
                  cancel_requested INTEGER NOT NULL DEFAULT 0,
                  error_code TEXT,
                  error_message TEXT,
                  error_retryable INTEGER NOT NULL DEFAULT 0,
                  created_at REAL NOT NULL,
                  updated_at REAL NOT NULL,
                  terminal_at REAL,
                  UNIQUE(profile_fingerprint, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_state_created ON jobs(state, created_at);
                CREATE INDEX IF NOT EXISTS idx_jobs_terminal_at ON jobs(terminal_at);
                """
            )
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
            if "error_retryable" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN error_retryable INTEGER NOT NULL DEFAULT 0")
            if "result_manifest_json" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN result_manifest_json TEXT")

    def recover_after_startup(self, valid_profile_fingerprints: set[str] | None = None) -> None:
        now = time.time()
        with self._lock, self._connect() as conn:
            if valid_profile_fingerprints is not None:
                if valid_profile_fingerprints:
                    placeholders = ",".join("?" for _ in valid_profile_fingerprints)
                    conn.execute(
                        f"""
                        UPDATE jobs SET state='failed', stage=NULL, error_code='profile_changed',
                          error_message='Engine profile changed across restart.', error_retryable=0, updated_at=?, terminal_at=?
                        WHERE state NOT IN ('succeeded','failed','cancelled','interrupted')
                          AND profile_fingerprint NOT IN ({placeholders})
                        """,
                        (now, now, *sorted(valid_profile_fingerprints)),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE jobs SET state='failed', stage=NULL, error_code='profile_changed',
                          error_message='No previously selected Engine profile is currently ready.', error_retryable=0, updated_at=?, terminal_at=?
                        WHERE state NOT IN ('succeeded','failed','cancelled','interrupted')
                        """,
                        (now, now),
                    )
            conn.execute(
                """
                UPDATE jobs SET state='interrupted', stage=NULL, error_code='job_interrupted',
                  error_message='Engine restarted while the job was running.', error_retryable=1, updated_at=?, terminal_at=?
                WHERE state IN ('running', 'cancel_requested')
                """,
                (now, now),
            )

    def create_or_get(self, request: CreateJobRequest, profile_fingerprint: str, request_fingerprint: str) -> tuple[dict[str, Any], bool]:
        now = time.time()
        ticket = uuid.uuid4().hex
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM jobs WHERE profile_fingerprint=? AND idempotency_key=?",
                (profile_fingerprint, request.idempotencyKey),
            ).fetchone()
            if existing:
                conn.execute("COMMIT")
                row = dict(existing)
                if row["request_fingerprint"] != request_fingerprint:
                    raise EngineApiError("idempotency_conflict", "Idempotency key was reused with a different payload.", 409)
                return row, False
            try:
                conn.execute(
                    """
                    INSERT INTO jobs(ticket,job_id,idempotency_key,request_fingerprint,source_sha256,source_bytes,source_mime,
                      processing_spec_json,profile_fingerprint,state,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,'awaiting_source',?,?)
                    """,
                    (
                        ticket,
                        request.jobId,
                        request.idempotencyKey,
                        request_fingerprint,
                        request.sourceSha256,
                        request.sourceBytes,
                        request.sourceMime,
                        request.processingSpec.model_dump_json(),
                        profile_fingerprint,
                        now,
                        now,
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return self.get(ticket), True

    def get(self, ticket: str) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE ticket=?", (ticket,)).fetchone()
        if not row:
            raise EngineApiError("job_not_found", "Unknown engine ticket.", 404)
        return dict(row)

    def list_queued(self, limit: int = 4) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created_at LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def mark_source_ready(self, ticket: str, path: Path) -> dict[str, Any]:
        now = time.time()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE jobs SET source_path=?, updated_at=? WHERE ticket=? AND state='awaiting_source'",
                (str(path), now, ticket),
            )
            if cur.rowcount != 1:
                row = self.get(ticket)
                if row["source_path"] == str(path):
                    return row
                raise EngineApiError("invalid_source", "Job is not awaiting source bytes.", 409)
        return self.get(ticket)

    def start(self, ticket: str) -> dict[str, Any]:
        now = time.time()
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE ticket=?", (ticket,)).fetchone()
            if not row:
                raise EngineApiError("job_not_found", "Unknown engine ticket.", 404)
            state = row["state"]
            if state in ("queued", "running", "succeeded"):
                return dict(row)
            if state == "interrupted" and row["source_path"]:
                conn.execute(
                    "UPDATE jobs SET state='queued', stage=NULL, progress_completed=NULL, progress_total=NULL, cancel_requested=0, error_code=NULL, error_message=NULL, error_retryable=0, terminal_at=NULL, updated_at=? WHERE ticket=?",
                    (now, ticket),
                )
                return self.get(ticket)
            if state != "awaiting_source" or not row["source_path"]:
                raise EngineApiError("invalid_source", "Source upload must complete before starting a job.", 409)
            conn.execute("UPDATE jobs SET state='queued', updated_at=? WHERE ticket=?", (now, ticket))
        return self.get(ticket)

    def claim(self, ticket: str) -> dict[str, Any] | None:
        now = time.time()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE jobs SET state='running', stage='decode', progress_completed=0, progress_total=10, updated_at=? WHERE ticket=? AND state='queued'",
                (now, ticket),
            )
            if cur.rowcount != 1:
                return None
        return self.get(ticket)

    def set_stage(self, ticket: str, stage: str, completed: int, total: int = 10) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET stage=?, progress_completed=?, progress_total=?, updated_at=? WHERE ticket=? AND state IN ('running','cancel_requested')",
                (stage, completed, total, time.time(), ticket),
            )

    def request_cancel(self, ticket: str) -> dict[str, Any]:
        now = time.time()
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE ticket=?", (ticket,)).fetchone()
            if not row:
                raise EngineApiError("job_not_found", "Unknown engine ticket.", 404)
            if row["state"] in TERMINAL_STATES and row["state"] != "interrupted":
                return dict(row)
            if row["state"] in {"awaiting_source", "queued", "interrupted"}:
                conn.execute(
                    "UPDATE jobs SET state='cancelled', cancel_requested=1, stage=NULL, error_code='job_cancelled', error_retryable=0, updated_at=?, terminal_at=? WHERE ticket=?",
                    (now, now, ticket),
                )
            else:
                conn.execute(
                    "UPDATE jobs SET state='cancel_requested', cancel_requested=1, updated_at=? WHERE ticket=?",
                    (now, ticket),
                )
        return self.get(ticket)

    def is_cancel_requested(self, ticket: str) -> bool:
        row = self.get(ticket)
        return bool(row["cancel_requested"])

    def mark_cancelled(self, ticket: str) -> None:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET state='cancelled', stage=NULL, error_code='job_cancelled', error_message='Job was cancelled.', error_retryable=0, updated_at=?, terminal_at=? WHERE ticket=?",
                (now, now, ticket),
            )

    def succeed(self, ticket: str, *, result_path: Path, result_mime: str, result_bytes: int, result_sha256: str, width: int, height: int, manifest: dict[str, object]) -> None:
        now = time.time()
        manifest_json = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs SET state='succeeded',stage='encode',progress_completed=10,progress_total=10,
                  result_path=?,result_mime=?,result_bytes=?,result_sha256=?,result_manifest_json=?,width=?,height=?,
                  error_code=NULL,error_message=NULL,error_retryable=0,updated_at=?,terminal_at=? WHERE ticket=?
                """,
                (str(result_path), result_mime, result_bytes, result_sha256, manifest_json, width, height, now, now, ticket),
            )

    def fail(self, ticket: str, code: str, message: str, *, retryable: bool = False) -> None:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET state='failed',stage=NULL,error_code=?,error_message=?,error_retryable=?,updated_at=?,terminal_at=? WHERE ticket=?",
                (code, message[:500], 1 if retryable else 0, now, now, ticket),
            )

    def delete(self, ticket: str) -> dict[str, Any]:
        row = self.get(ticket)
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM jobs WHERE ticket=?", (ticket,))
        return row

    def expired_terminal(self, cutoff: float) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE terminal_at IS NOT NULL AND terminal_at < ?",
                (cutoff,),
            ).fetchall()
        return [dict(row) for row in rows]
