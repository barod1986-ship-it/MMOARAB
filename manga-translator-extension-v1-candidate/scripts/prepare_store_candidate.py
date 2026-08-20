from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile

from release_evidence import validate_controlled_manifest
from v1_evidence_orchestrator import read_store_handoff
from pathlib import Path, PurePosixPath

EXPECTED_REQUIRED_PERMISSIONS = {"activeTab", "scripting", "storage", "sidePanel", "alarms"}
EXPECTED_OPTIONAL_HOSTS = {"https://*/*", "http://127.0.0.1/*"}
FORBIDDEN_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".env", ".map"}
FORBIDDEN_PREFIXES = ("engine/", "node_modules/", ".git/", "tests/", "store/")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote the exact tested extension ZIP to a Chrome Web Store candidate.")
    parser.add_argument("--zip", required=True, dest="zip_path")
    parser.add_argument("--tested-sha256", required=True)
    parser.add_argument("--out", default="release/store")
    parser.add_argument("--controlled-manifest")
    parser.add_argument("--store-submission-handoff")
    args = parser.parse_args()

    source = Path(args.zip_path).resolve()
    if not source.is_file():
        raise SystemExit(f"candidate ZIP not found: {source}")
    expected = args.tested_sha256.strip().lower()
    if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
        raise SystemExit("--tested-sha256 must be one lowercase/uppercase SHA-256 hex digest")
    actual = sha256_file(source)
    if actual != expected:
        raise SystemExit(f"tested ZIP hash mismatch: expected {expected}, got {actual}")

    controlled_binding = None
    if bool(args.controlled_manifest) != bool(args.store_submission_handoff):
        raise SystemExit("--controlled-manifest and --store-submission-handoff must be supplied together")
    if args.controlled_manifest:
        manifest, manifest_sha = validate_controlled_manifest(Path(args.controlled_manifest).resolve(), require_v1=True)
        handoff = read_store_handoff(Path(args.store_submission_handoff).resolve())
        if manifest.get("releaseClass") != "public-v1":
            raise SystemExit("Chrome Web Store controlled promotion requires a public-v1 manifest")
        extension = manifest.get("extension") if isinstance(manifest.get("extension"), dict) else {}
        if handoff.get("controlledManifestSha256") != manifest_sha:
            raise SystemExit("Store submission handoff does not match controlled manifest bytes")
        if handoff.get("releaseId") != manifest.get("releaseId") or handoff.get("assemblySourceHeadSha") != manifest.get("sourceHeadSha") or handoff.get("qualifiedSourceHeadSha") != manifest.get("qualifiedSourceHeadSha"):
            raise SystemExit("Store submission handoff release/source identity differs from controlled manifest")
        if handoff.get("extensionArtifact") != source.name or extension.get("artifact") != source.name:
            raise SystemExit("Store candidate must use the exact controlled Extension artifact filename")
        controlled_sha = str(extension.get("sha256", "")).lower().removeprefix("sha256:")
        if handoff.get("extensionSha256") != controlled_sha or actual != controlled_sha:
            raise SystemExit("Store candidate bytes differ from the controlled Extension/handoff")
        controlled_binding = {
            "releaseId": manifest["releaseId"],
            "controlledManifestSha256": manifest_sha,
            "storeSubmissionHandoffSha256": handoff["handoffSha256"],
            "orchestrationSessionSha256": handoff["orchestrationSessionSha256"],
            "assemblySourceHeadSha": manifest["sourceHeadSha"],
            "qualifiedSourceHeadSha": manifest["qualifiedSourceHeadSha"],
        }

    with zipfile.ZipFile(source, "r") as archive:
        infos = archive.infolist()
        normalized_names: set[str] = set()
        for info in infos:
            normalized = info.filename.replace("\\", "/")
            parts = PurePosixPath(normalized).parts
            if not normalized or normalized.startswith("/") or not parts or any(part in {".", ".."} for part in parts):
                raise SystemExit(f"unsafe ZIP path: {info.filename}")
            if ":" in parts[0]:
                raise SystemExit(f"unsafe ZIP drive/path prefix: {info.filename}")
            if normalized in normalized_names:
                raise SystemExit(f"duplicate ZIP path: {info.filename}")
            normalized_names.add(normalized)
            unix_mode = (info.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:
                raise SystemExit(f"symlink entries are forbidden in Store ZIP: {info.filename}")
            lower = normalized.lower()
            if any(lower.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
                raise SystemExit(f"forbidden Store ZIP content: {info.filename}")
            if Path(lower).suffix in FORBIDDEN_SUFFIXES:
                raise SystemExit(f"forbidden Store ZIP file type: {info.filename}")
        if "manifest.json" not in normalized_names:
            raise SystemExit("Store ZIP must contain manifest.json at archive root")
        manifest = json.loads(archive.read("manifest.json"))

    if manifest.get("manifest_version") != 3:
        raise SystemExit("Store candidate must be Manifest V3")
    try:
        minimum = int(str(manifest.get("minimum_chrome_version", "0")).split(".")[0])
    except ValueError:
        minimum = 0
    if minimum < 148:
        raise SystemExit("Store candidate minimum_chrome_version must be >= 148")
    if set(manifest.get("permissions", [])) != EXPECTED_REQUIRED_PERMISSIONS:
        raise SystemExit(f"required permission drift: {manifest.get('permissions', [])}")
    if set(manifest.get("optional_host_permissions", [])) != EXPECTED_OPTIONAL_HOSTS:
        raise SystemExit(f"optional host permission drift: {manifest.get('optional_host_permissions', [])}")
    if manifest.get("host_permissions"):
        raise SystemExit("Store candidate must not have required host_permissions")
    if manifest.get("message_serialization") != "structured_clone":
        raise SystemExit("Store candidate lost Chrome 148 structured-clone contract")

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    target = out / source.name
    shutil.copyfile(source, target)  # exact bytes; no re-zipping
    copied = sha256_file(target)
    if copied != actual:
        raise SystemExit("copy integrity failure")
    (out / "SHA256SUMS").write_text(f"{actual}  {target.name}\n", encoding="utf-8")
    metadata = {
        "schemaVersion": 2 if controlled_binding else 1,
        "artifact": target.name,
        "sha256": actual,
        "testedSha256": expected,
        "byteIdenticalToTestedZip": True,
        "byteIdenticalToControlledExtension": bool(controlled_binding),
        "manifestVersion": manifest.get("version"),
        "minimumChromeVersion": manifest.get("minimum_chrome_version"),
        "firstPublishMode": "manual-dashboard",
    }
    if controlled_binding:
        metadata.update(controlled_binding)
    (out / "candidate.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
