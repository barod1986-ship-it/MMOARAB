from __future__ import annotations

import asyncio
import hashlib
import io
import os
import sqlite3
import stat
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from PIL import Image, ImageChops

from mte_engine.app import create_app
from mte_engine.config import EngineSettings, PairingStore
from mte_engine.profile import current_profile_fingerprint
from mte_engine.constants import FIXTURE_PROFILE_ID

ORIGIN = "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
OTHER_ORIGIN = "chrome-extension://bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def arabic_font_path() -> Path:
    candidates = [
        Path("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/opentype/freefont/FreeSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    pytest.skip("No Arabic-capable test font is available in this environment.")



def png_bytes(width: int = 32, height: int = 24) -> bytes:
    image = Image.new("RGBA", (width, height), (230, 240, 250, 255))
    for x in range(4, 14):
        for y in range(5, 15):
            image.putpixel((x, y), (20, 30, 40, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def processing_spec() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "sourceLanguage": "en",
        "targetLanguage": "ar",
        "textRolePolicy": {
            "translatableKinds": ["dialogue", "narration"],
            "sfxAction": "preserve-original",
            "uncertainAction": "preserve-original",
            "revision": "sfx-preserve-v1",
        },
        "output": {"kind": "translated-raster-image", "preserveDimensions": True},
        "profileId": FIXTURE_PROFILE_ID,
    }


def job_body(payload: bytes, *, key: str = "sha256:" + "1" * 64, job_id: str = "job-test-1") -> dict[str, object]:
    return {
        "jobId": job_id,
        "idempotencyKey": key,
        "sourceSha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
        "sourceBytes": len(payload),
        "sourceMime": "image/png",
        "processingSpec": processing_spec(),
        "expectedProfileFingerprint": current_profile_fingerprint(FIXTURE_PROFILE_ID, font_path=arabic_font_path()),
    }


@pytest_asyncio.fixture
async def client(tmp_path: Path):
    settings = EngineSettings(data_dir=tmp_path, port=17891, arabic_font_path=arabic_font_path(), enable_fixture_profile=True)
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 44221))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:17891") as http:
            yield http, PairingStore(tmp_path), app


def auth(pairing: PairingStore, origin: str = ORIGIN) -> dict[str, str]:
    return {"Origin": origin, "Authorization": f"Bearer {pairing.token}"}


@pytest.mark.asyncio
async def test_health_pairing_host_and_exact_origin(client):
    http, pairing, _ = client
    health = await http.get("/healthz")
    assert health.status_code == 204

    assert (await http.get("/v1/capabilities", headers={"Origin": ORIGIN})).status_code == 401
    assert (await http.get("/v1/capabilities", headers={"Origin": ORIGIN, "Authorization": "Bearer wrong"})).status_code == 401

    preflight_before_pairing = await http.options(
        "/v1/capabilities",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"},
    )
    assert preflight_before_pairing.status_code == 204
    assert preflight_before_pairing.headers["access-control-allow-origin"] == ORIGIN

    caps = await http.get("/v1/capabilities", headers=auth(pairing))
    assert caps.status_code == 200
    body = caps.json()
    assert body["protocolVersion"] == 1
    assert body["profiles"][0]["state"] == "needs-download"
    fixture_profile = next(profile for profile in body["profiles"] if profile["profileId"] == FIXTURE_PROFILE_ID)
    assert fixture_profile["state"] == "ready" and fixture_profile["profileFingerprint"].startswith("sha256:")
    assert pairing.paired_origin == ORIGIN
    if os.name != "nt":
        assert stat.S_IMODE((pairing._path).stat().st_mode) == 0o600

    assert (await http.get("/v1/capabilities", headers=auth(pairing, OTHER_ORIGIN))).status_code == 401
    paired_preflight = await http.options(
        "/v1/jobs",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization, content-type"},
    )
    assert paired_preflight.status_code == 204
    other_preflight = await http.options(
        "/v1/jobs",
        headers={"Origin": OTHER_ORIGIN, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization, content-type"},
    )
    assert other_preflight.status_code == 403
    assert (await http.get("/healthz", headers={"Host": "evil.invalid"})).status_code == 403


@pytest.mark.asyncio
async def test_strict_schema_idempotency_no_url_fetch_and_source_guards(client):
    http, pairing, _ = client
    await http.get("/v1/capabilities", headers=auth(pairing))

    # Authentication must happen in middleware before FastAPI/Pydantic body parsing.
    unauthenticated_malformed = await http.post(
        "/v1/jobs",
        headers={"Origin": ORIGIN, "Content-Type": "application/json"},
        content=b"{not-json",
    )
    assert unauthenticated_malformed.status_code == 401

    payload = png_bytes()
    body = job_body(payload, job_id="job-ssrf-fixture")

    created = await http.post("/v1/jobs", headers=auth(pairing), json=body)
    assert created.status_code == 200
    ticket = created.json()["engineTicket"]
    repeated = await http.post("/v1/jobs", headers=auth(pairing), json=body)
    assert repeated.status_code == 200
    assert repeated.json()["engineTicket"] == ticket

    changed = dict(body)
    changed["sourceBytes"] = len(payload) + 1
    conflict = await http.post("/v1/jobs", headers=auth(pairing), json=changed)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"

    with_url = dict(job_body(payload, key="sha256:" + "2" * 64))
    with_url["imageUrl"] = "http://127.0.0.1:9/private"
    rejected = await http.post("/v1/jobs", headers=auth(pairing), json=with_url)
    assert rejected.status_code == 400

    bad_hash = await http.put(
        f"/v1/jobs/{ticket}/source",
        headers={**auth(pairing), "Content-Type": "image/png", "X-Source-SHA256": "sha256:" + "0" * 64},
        content=payload,
    )
    assert bad_hash.status_code == 400

    unknown = await http.get("/v1/jobs/not-a-real-ticket", headers=auth(pairing))
    assert unknown.status_code == 404
    traversal = await http.get("/v1/jobs/%2e%2e%2f%2e%2e%2fetc%2fpasswd", headers=auth(pairing))
    assert traversal.status_code in {404, 405}


@pytest.mark.asyncio
async def test_full_job_result_is_exact_lossless_and_release(client):
    http, pairing, app = client
    await http.get("/v1/capabilities", headers=auth(pairing))
    source = png_bytes(40, 28)
    body = job_body(source, key="sha256:" + "3" * 64)
    create = await http.post("/v1/jobs", headers=auth(pairing), json=body)
    ticket = create.json()["engineTicket"]

    upload = await http.put(
        f"/v1/jobs/{ticket}/source",
        headers={**auth(pairing), "Content-Type": "image/png", "X-Source-SHA256": body["sourceSha256"]},
        content=source,
    )
    assert upload.status_code == 200
    source_files = list((app.state.settings.data_dir / "spool" / "sources").glob("*.bin"))
    assert [path.name for path in source_files] == [f"{ticket}.bin"]
    if os.name != "nt":
        assert stat.S_IMODE(source_files[0].stat().st_mode) == 0o600
        assert stat.S_IMODE((app.state.settings.data_dir / "spool").stat().st_mode) == 0o700
    repeated_upload = await http.put(
        f"/v1/jobs/{ticket}/source",
        headers={**auth(pairing), "Content-Type": "image/png", "X-Source-SHA256": body["sourceSha256"]},
        content=source,
    )
    assert repeated_upload.status_code == 200
    assert [path.name for path in (app.state.settings.data_dir / "spool" / "sources").glob("*.bin")] == [f"{ticket}.bin"]

    # A stale/corrupted source path must not short-circuit an idempotent retry.
    tampered_source_path = app.state.settings.data_dir / "spool" / "sources" / f"{ticket}.bin"
    tampered_source_path.write_bytes(b"corrupt")
    repaired_upload = await http.put(
        f"/v1/jobs/{ticket}/source",
        headers={**auth(pairing), "Content-Type": "image/png", "X-Source-SHA256": body["sourceSha256"]},
        content=source,
    )
    assert repaired_upload.status_code == 200
    assert tampered_source_path.read_bytes() == source

    assert (await http.post(f"/v1/jobs/{ticket}/start", headers=auth(pairing))).status_code == 200

    status = None
    for _ in range(100):
        status = await http.get(f"/v1/jobs/{ticket}", headers=auth(pairing))
        assert status.status_code == 200
        if status.json()["state"] == "succeeded":
            break
        await asyncio.sleep(0.02)
    assert status is not None and status.json()["state"] == "succeeded"
    result_path = Path(str(app.state.jobs.get(ticket)["result_path"]))
    assert result_path.stem == ticket
    assert result_path.suffix in {".webp", ".png"}
    if os.name != "nt":
        assert stat.S_IMODE(result_path.stat().st_mode) == 0o600
        assert stat.S_IMODE((app.state.settings.data_dir / "jobs.sqlite3").stat().st_mode) == 0o600

    result = await http.get(f"/v1/jobs/{ticket}/result", headers=auth(pairing))
    assert result.status_code == 200
    assert result.headers["x-profile-fingerprint"] == current_profile_fingerprint(FIXTURE_PROFILE_ID, font_path=arabic_font_path())
    assert int(result.headers["x-image-width"]) == 40
    assert int(result.headers["x-image-height"]) == 28
    assert result.headers["x-result-sha256"] == "sha256:" + hashlib.sha256(result.content).hexdigest()

    with Image.open(io.BytesIO(source)) as before, Image.open(io.BytesIO(result.content)) as after:
        a = before.convert("RGBA")
        b = after.convert("RGBA")
        assert a.size == b.size
        assert ImageChops.difference(a, b).getbbox() is None

    manifest = await http.get(f"/v1/jobs/{ticket}/result-manifest", headers=auth(pairing))
    assert manifest.status_code == 200
    manifest_body = manifest.json()
    assert manifest_body["schemaVersion"] == 1 and manifest_body["jobId"] == body["jobId"] and manifest_body["blocks"] == []
    assert (await http.delete(f"/v1/jobs/{ticket}", headers=auth(pairing))).status_code == 204
    assert (await http.get(f"/v1/jobs/{ticket}", headers=auth(pairing))).status_code == 404


@pytest.mark.asyncio
async def test_cancel_and_pairing_reset(client):
    http, pairing, _ = client
    await http.get("/v1/capabilities", headers=auth(pairing))

    # Authentication must happen in middleware before FastAPI/Pydantic body parsing.
    unauthenticated_malformed = await http.post(
        "/v1/jobs",
        headers={"Origin": ORIGIN, "Content-Type": "application/json"},
        content=b"{not-json",
    )
    assert unauthenticated_malformed.status_code == 401

    payload = png_bytes()
    create = await http.post("/v1/jobs", headers=auth(pairing), json=job_body(payload, key="sha256:" + "4" * 64))
    ticket = create.json()["engineTicket"]
    cancel = await http.post(f"/v1/jobs/{ticket}/cancel", headers=auth(pairing))
    assert cancel.status_code == 200 and cancel.json()["state"] == "cancelled"

    old_token = pairing.token
    reset = await http.post("/v1/pairing/reset", headers=auth(pairing))
    assert reset.status_code == 204 and pairing.paired_origin is None
    assert reset.headers.get("access-control-allow-origin") == ORIGIN
    assert pairing.token != old_token
    # Reset rotates the secret: both the old token and a fresh unpaired token cannot access jobs.
    old_headers = {"Origin": ORIGIN, "Authorization": f"Bearer {old_token}"}
    assert (await http.get(f"/v1/jobs/{ticket}", headers=old_headers)).status_code == 401
    assert (await http.get(f"/v1/jobs/{ticket}", headers=auth(pairing))).status_code == 401


def test_engine_restart_marks_running_interrupted_and_same_ticket_can_restart(tmp_path: Path):
    # Use the repository underneath a real app-created schema; this test targets crash-state semantics.
    settings = EngineSettings(data_dir=tmp_path, port=17891, arabic_font_path=arabic_font_path(), enable_fixture_profile=True)
    app = create_app(settings)
    jobs = app.state.jobs
    payload = png_bytes()
    from mte_engine.models import CreateJobRequest
    import json
    request = CreateJobRequest.model_validate_json(json.dumps(job_body(payload, key="sha256:" + "5" * 64)))
    row, _ = jobs.create_or_get(request, current_profile_fingerprint(FIXTURE_PROFILE_ID, font_path=arabic_font_path()), "fixture-fingerprint")
    source_path = tmp_path / "spool" / "sources" / "recovery-source.bin"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(payload)
    jobs.mark_source_ready(row["ticket"], source_path)
    jobs.start(row["ticket"])
    assert jobs.claim(row["ticket"])["state"] == "running"
    jobs.recover_after_startup({current_profile_fingerprint(FIXTURE_PROFILE_ID, font_path=arabic_font_path())})
    assert jobs.get(row["ticket"])["state"] == "interrupted"
    restarted = jobs.start(row["ticket"])
    assert restarted["state"] == "queued"
    assert restarted["ticket"] == row["ticket"]


def test_settings_reject_non_loopback_bind(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MTE_ENGINE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MTE_ENGINE_HOST", "0.0.0.0")
    with pytest.raises(RuntimeError, match="127.0.0.1"):
        EngineSettings.from_env()


def test_settings_reject_nondefault_port(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MTE_ENGINE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MTE_ENGINE_PORT", "17892")
    with pytest.raises(RuntimeError, match="17891"):
        EngineSettings.from_env()


def test_profile_change_recovery_fails_old_nonterminal_identity(tmp_path: Path):
    settings = EngineSettings(data_dir=tmp_path, port=17891, arabic_font_path=arabic_font_path(), enable_fixture_profile=True)
    app = create_app(settings)
    jobs = app.state.jobs
    payload = png_bytes()
    from mte_engine.models import CreateJobRequest
    import json
    request = CreateJobRequest.model_validate_json(json.dumps(job_body(payload, key="sha256:" + "6" * 64)))
    row, _ = jobs.create_or_get(request, current_profile_fingerprint(FIXTURE_PROFILE_ID, font_path=arabic_font_path()), "profile-change-fixture")
    jobs.recover_after_startup({"sha256:" + "f" * 64})
    changed = jobs.get(row["ticket"])
    assert changed["state"] == "failed"
    assert changed["error_code"] == "profile_changed"
    assert changed["error_retryable"] == 0

@pytest.mark.asyncio
async def test_production_default_profile_is_fail_closed_until_benchmarked_models_are_pinned(tmp_path: Path):
    settings = EngineSettings(data_dir=tmp_path, port=17891, arabic_font_path=arabic_font_path(), enable_fixture_profile=False)
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 44221))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:17891") as http:
            pairing = PairingStore(tmp_path)
            caps = await http.get("/v1/capabilities", headers=auth(pairing))
            assert caps.status_code == 200
            profile = next(p for p in caps.json()["profiles"] if p["profileId"] == "default-v1")
            assert profile["state"] == "needs-download"
            payload = png_bytes()
            body = job_body(payload, key="sha256:" + "7" * 64)
            body["processingSpec"]["profileId"] = "default-v1"
            body["expectedProfileFingerprint"] = profile["profileFingerprint"]
            rejected = await http.post("/v1/jobs", headers=auth(pairing), json=body)
            assert rejected.status_code == 409
            assert rejected.json()["error"]["code"] == "profile_not_ready"
