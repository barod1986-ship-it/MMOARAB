from __future__ import annotations

import asyncio
import hashlib
import json
import time
from contextlib import asynccontextmanager, suppress
from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response

from .config import EngineSettings, PairingStore, is_valid_extension_origin
from .constants import (
    ENGINE_VERSION,
    MAX_RESULT_BYTES,
    MAX_SOURCE_BYTES,
    PROTOCOL_VERSION,
    RESULT_MANIFEST_SCHEMA_VERSION,
    SPOOL_TTL_SECONDS,
)
from .db import JobRepository, TERMINAL_STATES
from .consent import verify_remote_transfer_consent
from .errors import EngineApiError
from .models import CapabilitiesResponse, CreateJobRequest, HardwareDescriptor, ProfileDescriptor, StartJobRequest
from .model_install import (
    DistributionCatalog,
    ModelDownloadWorker,
    ModelInstaller,
    ModelInstallRepository,
    model_catalog_snapshot,
    model_install_status,
)
from .profile import current_profile_fingerprint, get_profile_descriptor, profile_descriptors, ready_profile_fingerprints
from .security import authenticate_request, peer_is_loopback
from .service import EngineWorker
from .spool import SpoolStore


def create_app(settings: EngineSettings | None = None) -> FastAPI:
    settings = settings or EngineSettings.from_env()
    settings = replace(
        settings,
        model_artifacts_dir=settings.model_artifacts_dir or (settings.data_dir / "models"),
        model_distribution_catalog_path=settings.model_distribution_catalog_path or (Path(__file__).resolve().parent / "resources" / "model-distribution-v1.json"),
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    pairing = PairingStore(settings.data_dir)
    jobs = JobRepository(settings.data_dir / "jobs.sqlite3")
    spool = SpoolStore(settings.data_dir)
    worker = EngineWorker(jobs, spool, settings)
    model_catalog_path = settings.model_distribution_catalog_path
    model_artifacts_dir = settings.model_artifacts_dir
    assert model_catalog_path is not None and model_artifacts_dir is not None
    model_catalog = DistributionCatalog(model_catalog_path)
    model_installs = ModelInstallRepository(settings.data_dir / "model-installs.sqlite3")
    model_installer = ModelInstaller(
        catalog=model_catalog, model_dir=model_artifacts_dir, data_dir=settings.data_dir, repository=model_installs
    )
    model_download_worker = ModelDownloadWorker(model_installer)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        spool.cleanup_temp_files(time.time() - SPOOL_TTL_SECONDS)
        await worker.start()
        await model_download_worker.start()
        cleanup_task = asyncio.create_task(_cleanup_loop(jobs, spool), name="mte-spool-cleanup")
        try:
            yield
        finally:
            cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await cleanup_task
            await model_download_worker.stop()
            await worker.stop()

    app = FastAPI(
        title="Manga Translator Local Engine",
        version=ENGINE_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.pairing = pairing
    app.state.jobs = jobs
    app.state.spool = spool
    app.state.worker = worker
    app.state.model_catalog = model_catalog
    app.state.model_installs = model_installs
    app.state.model_installer = model_installer
    app.state.model_download_worker = model_download_worker

    @app.exception_handler(EngineApiError)
    async def engine_error_handler(_: Request, exc: EngineApiError) -> JSONResponse:
        return JSONResponse(exc.envelope(), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "invalid_request", "message": "Request body failed strict protocol validation.", "retryable": False}},
            status_code=400,
        )

    @app.middleware("http")
    async def loopback_and_cors(request: Request, call_next):
        if request.client is None or not peer_is_loopback(request.client.host):
            return JSONResponse(EngineApiError("unauthorized", "Non-loopback peers are rejected.", 403).envelope(), status_code=403)
        if request.headers.get("host") != settings.expected_host_header:
            return JSONResponse(EngineApiError("unauthorized", "Unexpected Host header.", 403).envelope(), status_code=403)
        origin = request.headers.get("origin")
        if request.method == "OPTIONS":
            return _preflight_response(request, pairing)
        cors_allowed = bool(origin and _cors_origin_allowed(origin, request.url.path, pairing))

        # Authenticate sensitive V1 routes before FastAPI parses a JSON body. This keeps
        # unauthenticated loopback callers from spending parser/model-validation resources.
        if request.url.path.startswith("/v1/"):
            try:
                authenticate_request(request, pairing, allow_pairing=request.url.path == "/v1/capabilities")
            except EngineApiError as exc:
                response = JSONResponse(exc.envelope(), status_code=exc.status_code)
                return _finalize_response(response, origin=origin, cors_allowed=cors_allowed)

        response = await call_next(request)
        return _finalize_response(response, origin=origin, cors_allowed=cors_allowed)

    @app.get("/healthz")
    async def healthz() -> Response:
        return Response(status_code=204)

    @app.get("/v1/capabilities")
    async def capabilities(request: Request) -> dict[str, Any]:
        authenticate_request(request, pairing, allow_pairing=True)
        return CapabilitiesResponse(
            protocolVersion=1,
            engineVersion=ENGINE_VERSION,
            maxSourceBytes=MAX_SOURCE_BYTES,
            maxResultBytes=MAX_RESULT_BYTES,
            supportedOutputKinds=("translated-raster-image",),
            resultManifestSchemaVersions=(1,),
            supportedSourceLanguages=("auto", "ja", "ko", "zh-Hans", "zh-Hant", "en"),
            supportedTargetLanguages=("ar",),
            recommendedDefaults={"sourceLanguage": "en", "targetLanguage": "ar"},
            hardware=HardwareDescriptor(cpu=True, cuda=False, rocm=False, metal=False, vulkan=False),
            recommendedConcurrency=1,
            profiles=tuple(ProfileDescriptor(**descriptor) for descriptor in profile_descriptors(settings)),
        ).model_dump()

    @app.get("/v1/setup/models")
    async def setup_models(request: Request) -> dict[str, object]:
        authenticate_request(request, pairing)
        return model_catalog_snapshot(model_catalog, model_installer)

    @app.post("/v1/setup/models/{artifact_id}/install")
    async def install_model(artifact_id: str, request: Request) -> dict[str, object]:
        authenticate_request(request, pairing)
        artifact = model_catalog.require(artifact_id)
        if model_installer.installed(artifact):
            return {
                "artifactId": artifact.artifact_id,
                "state": "ready",
                "downloadedBytes": artifact.bytes,
                "totalBytes": artifact.bytes,
            }
        row = model_installs.create_or_resume(artifact.artifact_id, artifact.bytes)
        model_download_worker.wake()
        return model_install_status(row)

    @app.get("/v1/setup/model-installs/{ticket}")
    async def model_install(ticket: str, request: Request) -> dict[str, object]:
        authenticate_request(request, pairing)
        return model_install_status(model_installs.get(ticket))

    @app.post("/v1/setup/model-installs/{ticket}/cancel")
    async def cancel_model_install(ticket: str, request: Request) -> dict[str, object]:
        authenticate_request(request, pairing)
        row = model_installs.cancel(ticket)
        model_download_worker.wake()
        return model_install_status(row)

    @app.post("/v1/jobs")
    async def create_job(request: Request, body: CreateJobRequest) -> dict[str, Any]:
        authenticate_request(request, pairing)
        if body.sourceBytes > MAX_SOURCE_BYTES:
            raise EngineApiError("source_too_large", "Source exceeds the V1 32 MiB limit.", 413)
        try:
            descriptor = get_profile_descriptor(settings, body.processingSpec.profileId)
        except KeyError as exc:
            raise EngineApiError("profile_not_found", "Requested profile is not available.", 404, details={"profileId": body.processingSpec.profileId}) from exc
        if descriptor["state"] != "ready":
            raise EngineApiError("profile_not_ready", "Requested Engine profile is not ready.", 409, details={"profileId": body.processingSpec.profileId, "state": descriptor["state"]})
        profile = descriptor["profileFingerprint"]
        if body.expectedProfileFingerprint != profile:
            raise EngineApiError("profile_changed", "Engine profile fingerprint changed before submission.", 409, details={"profileId": body.processingSpec.profileId})
        verify_remote_transfer_consent(descriptor, body.remoteTransferConsent)
        request_fingerprint = _create_request_fingerprint(body)
        row, _ = jobs.create_or_get(body, profile, request_fingerprint)
        return _create_response(row)

    @app.put("/v1/jobs/{ticket}/source")
    async def upload_source(ticket: str, request: Request) -> dict[str, Any]:
        authenticate_request(request, pairing)
        row = jobs.get(ticket)
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared_bytes = int(content_length)
            except ValueError as exc:
                raise EngineApiError("invalid_source", "Invalid Content-Length header.", 400) from exc
            if declared_bytes != int(row["source_bytes"]) or declared_bytes > MAX_SOURCE_BYTES:
                raise EngineApiError("source_too_large", "Content-Length does not match the declared source size.", 413)
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != row["source_mime"]:
            raise EngineApiError("invalid_source", "Upload Content-Type does not match job metadata.", 400)
        declared_hash = request.headers.get("x-source-sha256")
        if declared_hash != row["source_sha256"]:
            raise EngineApiError("source_hash_mismatch", "Upload SHA-256 header does not match job metadata.", 400)
        if row.get("source_path"):
            existing = Path(str(row["source_path"]))
            if spool.verify_file(existing, expected_bytes=int(row["source_bytes"]), expected_sha256=str(row["source_sha256"])):
                return {"state": row["state"]}
            spool.safe_unlink(str(existing))
        path = await spool.ingest_source(request, ticket=str(row["ticket"]), expected_bytes=int(row["source_bytes"]), expected_sha256=str(row["source_sha256"]))
        jobs.mark_source_ready(ticket, path)
        return {"state": "awaiting_source"}

    @app.post("/v1/jobs/{ticket}/start")
    async def start_job(ticket: str, request: Request, body: StartJobRequest | None = None) -> dict[str, Any]:
        authenticate_request(request, pairing)
        before = jobs.get(ticket)
        spec = json.loads(str(before["processing_spec_json"]))
        try:
            descriptor = get_profile_descriptor(settings, str(spec["profileId"]))
        except KeyError as exc:
            raise EngineApiError("profile_not_found", "Requested profile is no longer available.", 404) from exc
        if descriptor["state"] != "ready":
            raise EngineApiError("profile_not_ready", "Engine profile is no longer ready.", 409, details={"state": descriptor["state"]})
        if before["profile_fingerprint"] != descriptor["profileFingerprint"]:
            raise EngineApiError("profile_changed", "Engine profile changed before job restart.", 409)
        verify_remote_transfer_consent(descriptor, body.remoteTransferConsent if body is not None else None)
        row = jobs.start(ticket)
        worker.wake()
        return {"state": row["state"] if row["state"] != "awaiting_source" else "queued"}

    @app.get("/v1/jobs/{ticket}")
    async def get_job(ticket: str, request: Request) -> dict[str, Any]:
        authenticate_request(request, pairing)
        return _status_response(jobs.get(ticket))

    @app.post("/v1/jobs/{ticket}/cancel")
    async def cancel_job(ticket: str, request: Request) -> dict[str, Any]:
        authenticate_request(request, pairing)
        row = jobs.request_cancel(ticket)
        return {"state": row["state"]}

    @app.get("/v1/jobs/{ticket}/result")
    async def get_result(ticket: str, request: Request) -> Response:
        authenticate_request(request, pairing)
        row = jobs.get(ticket)
        if row["state"] != "succeeded" or not row.get("result_path"):
            raise EngineApiError("result_not_ready", "Job result is not ready.", 409, retryable=row["state"] in {"queued", "running", "cancel_requested"})
        path = Path(str(row["result_path"]))
        if not path.is_file():
            raise EngineApiError("internal_error", "Result spool artifact is missing.", 500)
        headers = {
            "X-Result-SHA256": str(row["result_sha256"]),
            "X-Image-Width": str(row["width"]),
            "X-Image-Height": str(row["height"]),
            "X-Profile-Fingerprint": str(row["profile_fingerprint"]),
            "Content-Length": str(row["result_bytes"]),
        }
        return FileResponse(path, media_type=str(row["result_mime"]), headers=headers)

    @app.get("/v1/jobs/{ticket}/result-manifest")
    async def result_manifest(ticket: str, request: Request) -> dict[str, Any]:
        authenticate_request(request, pairing)
        row = jobs.get(ticket)
        if row["state"] != "succeeded" or not row.get("result_manifest_json"):
            raise EngineApiError("result_not_ready", "Job result manifest is not ready.", 409)
        try:
            payload = json.loads(str(row["result_manifest_json"]))
        except json.JSONDecodeError as exc:
            raise EngineApiError("internal_error", "Stored result manifest is malformed.", 500) from exc
        return payload

    @app.delete("/v1/jobs/{ticket}")
    async def release_job(ticket: str, request: Request) -> Response:
        authenticate_request(request, pairing)
        row = jobs.delete(ticket)
        spool.safe_unlink(row.get("source_path"))
        spool.safe_unlink(row.get("result_path"))
        return Response(status_code=204)

    @app.post("/v1/pairing/reset")
    async def reset_pairing(request: Request) -> Response:
        authenticate_request(request, pairing)
        pairing.reset_pairing()
        return Response(status_code=204)

    @app.get("/v1/diagnostics")
    async def diagnostics(request: Request) -> dict[str, Any]:
        authenticate_request(request, pairing)
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "engineVersion": ENGINE_VERSION,
            "bind": settings.expected_host_header,
            "paired": pairing.paired_origin is not None,
            "profiles": profile_descriptors(settings),
            "readyProfileFingerprints": sorted(ready_profile_fingerprints(settings)),
        }

    return app


def _finalize_response(response: Response, *, origin: str | None, cors_allowed: bool) -> Response:
    if origin and cors_allowed:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    response.headers["Cache-Control"] = "no-store"
    return response


def _create_request_fingerprint(body: CreateJobRequest) -> str:
    payload = {
        "sourceSha256": body.sourceSha256,
        "sourceBytes": body.sourceBytes,
        "sourceMime": body.sourceMime,
        "processingSpec": body.processingSpec.model_dump(mode="json"),
        "expectedProfileFingerprint": body.expectedProfileFingerprint,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _create_response(row: dict[str, Any]) -> dict[str, Any]:
    response: dict[str, Any] = {
        "engineTicket": row["ticket"],
        "state": row["state"],
        "profileFingerprint": row["profile_fingerprint"],
    }
    if row["state"] == "succeeded":
        response["state"] = "completed"
        response["result"] = _result_descriptor(row)
    return response


def _status_response(row: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {"state": row["state"], "updatedAt": _iso(row["updated_at"])}
    if row.get("stage"):
        payload["stage"] = row["stage"]
    if row.get("progress_total"):
        payload["progress"] = {"completed": int(row["progress_completed"] or 0), "total": int(row["progress_total"])}
    if row["state"] == "succeeded":
        payload["result"] = _result_descriptor(row)
    if row.get("error_code"):
        payload["error"] = {"code": row["error_code"], "message": row.get("error_message") or row["error_code"], "retryable": bool(row.get("error_retryable"))}
    return payload


def _result_descriptor(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "mime": row["result_mime"],
        "bytes": int(row["result_bytes"]),
        "sha256": row["result_sha256"],
        "width": int(row["width"]),
        "height": int(row["height"]),
        "manifestAvailable": True,
    }


def _iso(timestamp: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _cors_origin_allowed(origin: str, path: str, pairing: PairingStore) -> bool:
    paired = pairing.paired_origin
    if paired is not None:
        return origin == paired
    return path == "/v1/capabilities" and is_valid_extension_origin(origin)


def _preflight_response(request: Request, pairing: PairingStore) -> Response:
    origin = request.headers.get("origin") or ""
    requested_method = request.headers.get("access-control-request-method") or ""
    requested_headers = request.headers.get("access-control-request-headers") or ""
    if requested_method not in {"GET", "POST", "PUT", "DELETE"}:
        return Response(status_code=403)
    if not _cors_origin_allowed(origin, request.url.path, pairing):
        return Response(status_code=403)
    allowed_headers = {"authorization", "content-type", "x-source-sha256"}
    incoming = {part.strip().lower() for part in requested_headers.split(",") if part.strip()}
    if not incoming.issubset(allowed_headers):
        return Response(status_code=403)
    return Response(
        status_code=204,
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": requested_method,
            "Access-Control-Allow-Headers": ", ".join(sorted(incoming)),
            "Access-Control-Max-Age": "600",
            "Vary": "Origin",
        },
    )


async def _cleanup_loop(jobs: JobRepository, spool: SpoolStore) -> None:
    while True:
        await asyncio.sleep(60 * 60)
        cutoff = time.time() - SPOOL_TTL_SECONDS
        spool.cleanup_temp_files(cutoff)
        for row in jobs.expired_terminal(cutoff):
            try:
                deleted = jobs.delete(str(row["ticket"]))
            except EngineApiError:
                continue
            spool.safe_unlink(deleted.get("source_path"))
            spool.safe_unlink(deleted.get("result_path"))
