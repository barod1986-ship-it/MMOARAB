from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import ipaddress
import ssl
import sys
import tempfile
import zipfile
import stat
from pathlib import PurePosixPath
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.acquisition import (
    AcquisitionError,
    acquisition_record_digest,
    load_source_registry,
    source_for_artifact,
    source_registry_digest,
    validate_acquisition_record,
)
from mte_engine.benchmark.catalog import artifact_by_id, load_catalog
from mte_engine.benchmark.common import sha256_path
from mte_engine.benchmark.provenance import artifact_stats

CHUNK = 1024 * 1024
USER_AGENT = "MTE-Production-Artifact-Acquirer/1"


def _host_allowed(hostname: str | None, suffixes: list[str]) -> bool:
    if not hostname:
        return False
    host = hostname.lower().rstrip(".")
    return any(host == suffix.lower().lstrip(".").rstrip(".") or host.endswith("." + suffix.lower().lstrip(".").rstrip(".")) for suffix in suffixes)


def _require_public_dns(hostname: str) -> None:
    try:
        infos = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise AcquisitionError(f"DNS resolution failed for registered host {hostname}: {exc}") from exc
    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise AcquisitionError(f"DNS resolution returned no addresses for registered host {hostname}")
    for value in addresses:
        try:
            address = ipaddress.ip_address(value.split("%", 1)[0])
        except ValueError as exc:
            raise AcquisitionError(f"DNS returned a malformed address for {hostname}: {value}") from exc
        if not address.is_global:
            raise AcquisitionError(f"refusing non-public address for registered host {hostname}: {address}")


def _redacted_url(value: str) -> str:
    parsed = urlparse(value)
    return parsed._replace(params="", query="", fragment="").geturl()


class _AllowlistedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, suffixes: list[str]) -> None:
        super().__init__()
        self.suffixes = suffixes

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        parsed = urlparse(newurl)
        if parsed.scheme != "https" or parsed.username or parsed.password or not _host_allowed(parsed.hostname, self.suffixes):
            raise AcquisitionError(f"refusing redirect outside registered HTTPS hosts: {parsed.hostname or '<invalid>'}")
        _require_public_dns(parsed.hostname)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener(host_suffixes: list[str]) -> urllib.request.OpenerDirector:
    context = ssl.create_default_context()
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context),
        _AllowlistedRedirectHandler(host_suffixes),
    )


def _download(url: str, target: Path, *, max_bytes: int, host_suffixes: list[str]) -> dict[str, object]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or not _host_allowed(parsed.hostname, host_suffixes):
        raise AcquisitionError(f"refusing unregistered retrieval URL: {url}")
    _require_public_dns(parsed.hostname)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
    opener = _opener(host_suffixes)
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    total = 0
    try:
        with opener.open(request, timeout=90) as response, target.open("xb") as stream:
            resolved = response.geturl()
            resolved_parsed = urlparse(resolved)
            if resolved_parsed.scheme != "https" or not _host_allowed(resolved_parsed.hostname, host_suffixes):
                raise AcquisitionError(f"resolved URL is outside registered HTTPS hosts: {resolved}")
            length = response.headers.get("Content-Length")
            if length is not None:
                try:
                    declared = int(length)
                except ValueError as exc:
                    raise AcquisitionError("server returned malformed Content-Length") from exc
                if declared <= 0 or declared > max_bytes:
                    raise AcquisitionError(f"server Content-Length is outside the registered bound: {declared}")
            while True:
                chunk = response.read(CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise AcquisitionError(f"download exceeded registered maximum of {max_bytes} bytes")
                digest.update(chunk)
                stream.write(chunk)
            if total <= 0:
                raise AcquisitionError("downloaded artifact file is empty")
            stream.flush()
            os.fsync(stream.fileno())
            return {
                "requestedUrl": url,
                "resolvedUrl": _redacted_url(resolved),
                "sha256": "sha256:" + digest.hexdigest(),
                "byteSize": total,
            }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AcquisitionError(f"download failed for {url}: {exc}") from exc


def _plan(source: dict, artifact_id: str) -> dict:
    if source["mode"] == "direct-https-file":
        retrievals = [{"path": source["expectedFilename"], "url": source["retrievalUrl"], "maxBytes": source["maxBytes"]}]
    elif source["mode"] == "https-tree":
        retrievals = [
            {
                "path": item["path"],
                "url": source["baseUrl"] + item["path"],
                "maxBytes": item["maxBytes"],
                "expectedSha256": item.get("sha256"),
            }
            for item in source["files"]
        ]
    elif source["mode"] == "https-zip-member":
        retrievals = [{
            "path": source["expectedFilename"], "url": source["retrievalUrl"],
            "maxBytes": source["maxBytes"], "sourceArchiveMember": source["archiveMember"],
            "maxArchiveBytes": source["maxArchiveBytes"],
        }]
    else:
        retrievals = []
    return {
        "artifactId": artifact_id,
        "mode": source["mode"],
        "upstreamRevision": source["upstreamRevision"],
        "expectedFilename": source["expectedFilename"],
        "retrievals": retrievals,
    }



def _safe_archive_member(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or normalized.startswith("/") or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise AcquisitionError("registered ZIP member path is unsafe")
    return path


def _extract_exact_zip_member(archive: Path, target: Path, *, member_path: str, max_bytes: int) -> dict[str, object]:
    expected = _safe_archive_member(member_path).as_posix()
    try:
        zf = zipfile.ZipFile(archive)
    except (OSError, zipfile.BadZipFile) as exc:
        raise AcquisitionError("downloaded source archive is not a valid ZIP") from exc
    with zf:
        matches = [info for info in zf.infolist() if not info.is_dir() and info.filename.replace("\\", "/") == expected]
        if len(matches) != 1:
            raise AcquisitionError(f"downloaded source ZIP does not contain exactly one registered member: {expected}")
        info = matches[0]
        mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(mode):
            raise AcquisitionError("registered ZIP member is a symlink")
        if info.file_size <= 0 or info.file_size > max_bytes:
            raise AcquisitionError("registered ZIP member size is outside the configured bound")
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(); total = 0
        with zf.open(info, "r") as src, target.open("xb") as dst:
            while True:
                chunk = src.read(CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise AcquisitionError("registered ZIP member exceeded the configured bound while extracting")
                digest.update(chunk); dst.write(chunk)
            dst.flush(); os.fsync(dst.fileno())
        if total != info.file_size:
            raise AcquisitionError("registered ZIP member extracted byte count mismatch")
        return {"sha256": "sha256:" + digest.hexdigest(), "byteSize": total, "memberPath": expected}

def main() -> int:
    parser = argparse.ArgumentParser(description="Acquire a production artifact only from the allowlisted primary-source registry and emit a content-addressed acquisition record. This command never approves licenses or benchmark use.")
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--source-registry", required=True, type=Path)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--records-dir", required=True, type=Path)
    parser.add_argument("--download", action="store_true", help="Perform network I/O. Without this flag only the exact retrieval plan is printed.")
    parser.add_argument("--replace", action="store_true", help="Replace existing acquired bytes/record transactionally.")
    args = parser.parse_args()

    catalog = load_catalog(args.catalog)
    catalog_item = artifact_by_id(catalog).get(args.artifact_id)
    if catalog_item is None:
        raise SystemExit(f"Unknown artifactId: {args.artifact_id}")
    registry = load_source_registry(args.source_registry)
    source = source_for_artifact(registry, args.artifact_id)
    if source["expectedFilename"] != catalog_item["expectedFilename"]:
        raise SystemExit("Source registry expectedFilename does not match catalog")
    if source["upstreamRevision"] != catalog_item["upstreamRevision"]:
        raise SystemExit("Source registry upstreamRevision does not match catalog")
    plan = _plan(source, args.artifact_id)
    if not args.download:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if source["mode"] not in {"direct-https-file", "https-tree", "https-zip-member"}:
        raise SystemExit(f"Artifact {args.artifact_id} requires reviewed manual acquisition/derivation; automated download is intentionally disabled")

    destination = args.output_dir / source["expectedFilename"]
    record_path = args.records_dir / f"{args.artifact_id}.acquisition.json"
    if (destination.exists() or record_path.exists()) and not args.replace:
        raise SystemExit("Destination or acquisition record already exists; use --replace only after intentionally reviewing the replacement")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.records_dir.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=".mte-acquire-", dir=args.output_dir))
    staged_artifact = staging_root / source["expectedFilename"]
    files: list[dict[str, object]] = []
    try:
        source_container = None
        if source["mode"] == "direct-https-file":
            detail = _download(source["retrievalUrl"], staged_artifact, max_bytes=int(source["maxBytes"]), host_suffixes=list(source["allowedHostSuffixes"]))
            files.append({"path": source["expectedFilename"], **detail})
        elif source["mode"] == "https-zip-member":
            archive_path = staging_root / ".source.zip"
            archive_detail = _download(source["retrievalUrl"], archive_path, max_bytes=int(source["maxArchiveBytes"]), host_suffixes=list(source["allowedHostSuffixes"]))
            extracted = _extract_exact_zip_member(archive_path, staged_artifact, member_path=str(source["archiveMember"]), max_bytes=int(source["maxBytes"]))
            files.append({
                "path": source["expectedFilename"], "requestedUrl": archive_detail["requestedUrl"],
                "resolvedUrl": archive_detail["resolvedUrl"], "sha256": extracted["sha256"], "byteSize": extracted["byteSize"],
            })
            source_container = {"kind":"zip","sha256":archive_detail["sha256"],"byteSize":archive_detail["byteSize"],"memberPath":extracted["memberPath"]}
            archive_path.unlink(missing_ok=True)
        else:
            staged_artifact.mkdir(parents=True, exist_ok=False)
            for item in source["files"]:
                relative = Path(item["path"])
                detail = _download(source["baseUrl"] + item["path"], staged_artifact / relative, max_bytes=int(item["maxBytes"]), host_suffixes=list(source["allowedHostSuffixes"]))
                expected = item.get("sha256")
                if expected is not None and detail["sha256"] != expected:
                    raise AcquisitionError(f"downloaded SHA-256 does not match registered pin for {item['path']}")
                files.append({"path": item["path"], **detail})

        artifact_digest = sha256_path(staged_artifact)
        artifact_bytes, artifact_files = artifact_stats(staged_artifact)
        acquired_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        record = {
            "schemaVersion": 1,
            "recordId": f"{args.artifact_id}-{artifact_digest.removeprefix('sha256:')[:16]}",
            "artifactId": args.artifact_id,
            "sourceRegistryRevision": registry["registryRevision"],
            "sourceRegistrySha256": source_registry_digest(registry),
            "catalogRevision": catalog["catalogRevision"],
            "expectedFilename": source["expectedFilename"],
            "upstreamRevision": source["upstreamRevision"],
            "acquiredAtUtc": acquired_at,
            "artifactSha256": artifact_digest,
            "artifactByteSize": artifact_bytes,
            "artifactFileCount": artifact_files,
            "files": files,
        }
        if source_container is not None:
            record["sourceContainer"] = source_container
        record["recordSha256"] = acquisition_record_digest(record)
        validate_acquisition_record(record, registry=registry, artifact_id=args.artifact_id, artifact_path=staged_artifact)

        record_tmp = record_path.with_suffix(record_path.suffix + ".tmp")
        record_tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        destination.parent.mkdir(parents=True, exist_ok=True)
        record_path.parent.mkdir(parents=True, exist_ok=True)
        backup_destination = destination.with_name(destination.name + ".mte-backup")
        backup_record = record_path.with_name(record_path.name + ".mte-backup")
        for backup in (backup_destination, backup_record):
            if backup.exists():
                raise AcquisitionError(f"stale acquisition backup must be reviewed before retry: {backup.name}")
        destination_backed_up = False
        record_backed_up = False
        artifact_promoted = False
        record_promoted = False
        try:
            if destination.exists():
                if not args.replace:
                    raise AcquisitionError("artifact destination appeared during acquisition")
                destination.replace(backup_destination)
                destination_backed_up = True
            if record_path.exists():
                if not args.replace:
                    raise AcquisitionError("acquisition record appeared during acquisition")
                record_path.replace(backup_record)
                record_backed_up = True
            staged_artifact.replace(destination)
            artifact_promoted = True
            record_tmp.replace(record_path)
            record_promoted = True
        except Exception:
            if record_promoted and record_path.exists():
                record_path.unlink()
            if artifact_promoted and destination.exists():
                if destination.is_dir():
                    shutil.rmtree(destination)
                else:
                    destination.unlink()
            if record_backed_up and backup_record.exists():
                backup_record.replace(record_path)
            if destination_backed_up and backup_destination.exists():
                backup_destination.replace(destination)
            raise
        else:
            if backup_record.exists():
                backup_record.unlink()
            if backup_destination.exists():
                if backup_destination.is_dir():
                    shutil.rmtree(backup_destination)
                else:
                    backup_destination.unlink()
        print(json.dumps({"artifact": str(destination), "record": str(record_path), "artifactSha256": artifact_digest, "recordSha256": record["recordSha256"]}, ensure_ascii=False, indent=2))
        return 0
    finally:
        try:
            tmp = record_path.with_suffix(record_path.suffix + ".tmp")
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        shutil.rmtree(staging_root, ignore_errors=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AcquisitionError as exc:
        raise SystemExit(str(exc))
