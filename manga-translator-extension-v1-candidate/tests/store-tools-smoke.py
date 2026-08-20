from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, cwd: Path = ROOT, expect: int = 0) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if proc.returncode != expect:
        raise AssertionError(f"expected exit {expect}, got {proc.returncode}: {' '.join(args)}\n{proc.stdout}")
    return proc


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_exact_candidate_promotion(tmp: Path) -> None:
    source = tmp / "candidate.zip"
    manifest = {
        "manifest_version": 3,
        "version": "0.8.0",
        "minimum_chrome_version": "148",
        "permissions": ["activeTab", "scripting", "storage", "sidePanel", "alarms"],
        "optional_host_permissions": ["https://*/*", "http://127.0.0.1/*"],
        "message_serialization": "structured_clone",
    }
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("background.js", "export {};\n")
    expected = digest(source)
    out = tmp / "promoted"
    run(sys.executable, str(ROOT / "scripts/prepare_store_candidate.py"), "--zip", str(source), "--tested-sha256", expected, "--out", str(out))
    target = out / source.name
    assert target.read_bytes() == source.read_bytes()
    metadata = json.loads((out / "candidate.json").read_text())
    assert metadata["byteIdenticalToTestedZip"] is True
    assert metadata["sha256"] == metadata["testedSha256"] == expected

    bad = run(sys.executable, str(ROOT / "scripts/prepare_store_candidate.py"), "--zip", str(source), "--tested-sha256", "0" * 64, "--out", str(tmp / "bad"), expect=1)
    assert "tested ZIP hash mismatch" in bad.stdout

    traversal = tmp / "traversal.zip"
    with zipfile.ZipFile(traversal, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("../secret.txt", "forbidden")
    bad_path = run(sys.executable, str(ROOT / "scripts/prepare_store_candidate.py"), "--zip", str(traversal), "--tested-sha256", digest(traversal), "--out", str(tmp / "traversal-out"), expect=1)
    assert "unsafe ZIP path" in bad_path.stdout


def test_release_gate_can_pass_when_real_inputs_exist(tmp: Path) -> None:
    (tmp / "scripts").mkdir()
    (tmp / "store/release").mkdir(parents=True)
    (tmp / "store/privacy").mkdir(parents=True)
    (tmp / "release/store").mkdir(parents=True)
    shutil.copyfile(ROOT / "scripts/verify-store-release-ready.mjs", tmp / "scripts/verify-store-release-ready.mjs")

    artifact = tmp / "release/store/store.zip"
    artifact.write_bytes(b"tested-store-zip-bytes")
    sha = digest(artifact)
    publisher_keys = ["developerAccountRegistered", "registrationFeePaid", "twoStepVerificationVerified", "supportContactVerified", "publisherOwnershipVerified"]
    dashboard_keys = ["storeListingCompleted", "privacyTabCompleted", "distributionCompleted", "reviewerTestInstructionsCompleted", "firstManualUploadCompleted", "firstManualSubmissionCompleted"]
    url_keys = ["privacyPolicy", "homepage", "support", "reviewerFixture", "engineDownload"]
    state = {
        "publicDistributionChosen": True,
        "publisher": {key: True for key in publisher_keys},
        "publicUrls": {key: f"https://example.invalid/{key}" for key in url_keys},
        "dashboard": {key: True for key in dashboard_keys},
        "releaseGates": {
            "phase5bProductionFreezeReady": True,
            "phase7NativeSupportReady": True,
            "chrome148StoreSmokePassed": True,
            "currentStableStoreSmokePassed": True,
            "testedZipSha256": None,
            "storeCandidateZipSha256": None,
        },
    }
    (tmp / "store/publication-state.json").write_text(json.dumps(state))
    (tmp / "store/release/profile-privacy.json").write_text(json.dumps({
        "schemaVersion": 2,
        "profileId": "default-v1",
        "profileFingerprintsByTarget": {
            "linux-x86_64": "a" * 64,
            "macos-arm64": "b" * 64,
            "windows-x86_64": "c" * 64,
        },
        "privacyDescriptor": {"imageLeavesDevice": False, "ocrTextLeavesDevice": False, "visualContextLeavesDevice": False},
        "remoteTransferConsentImplemented": False,
        "externalProviderNames": [],
        "materializedFromControlledManifestSha256": "d" * 64,
        "sourceHeadSha": "e" * 40,
    }))
    (tmp / "store/privacy/privacy-policy.md").write_text("# Privacy\nSupport: support@example.invalid\n")
    (tmp / "release/store/candidate.json").write_text(json.dumps({
        "schemaVersion": 2,
        "byteIdenticalToTestedZip": True,
        "byteIdenticalToControlledExtension": True,
        "controlledManifestSha256": "1" * 64,
        "storeSubmissionHandoffSha256": "2" * 64,
        "orchestrationSessionSha256": "3" * 64,
        "assemblySourceHeadSha": "4" * 40,
        "qualifiedSourceHeadSha": "5" * 40,
        "sha256": sha,
        "testedSha256": sha,
        "artifact": artifact.name,
    }))
    out = run("node", "scripts/verify-store-release-ready.mjs", cwd=tmp)
    assert "release-ready gate passed" in out.stdout


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mte-store-promote-") as raw:
        path = Path(raw)
        path.mkdir(exist_ok=True)
        test_exact_candidate_promotion(path)
    with tempfile.TemporaryDirectory(prefix="mte-store-ready-") as raw:
        test_release_gate_can_pass_when_real_inputs_exist(Path(raw))
    print("Phase 8 Store tooling smoke: 2/2 passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
