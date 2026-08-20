from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.qualification_bundle import QualificationBundleError, resolve_below, verify_qualification_input_bundle

EXPECTED = {
    "node": "v24.19.0",
    "npm": "12.0.2",
    "python": "3.13.15",
    "uv": "0.12.5",
}

NETWORK_TARGETS = [
    ("registry.npmjs.org", 443, "npm-registry"),
    ("pypi.org", 443, "python-index"),
    ("paddle-model-ecology.bj.bcebos.com", 443, "paddle-artifacts"),
    ("huggingface.co", 443, "manga-ocr-artifact"),
    ("github.com", 443, "font/source-metadata"),
]


def _run_version(argv: list[str]) -> dict[str, Any]:
    exe = shutil.which(argv[0])
    if not exe:
        return {"present": False, "value": None, "command": argv}
    try:
        cp = subprocess.run(argv, check=False, text=True, capture_output=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"present": True, "value": None, "command": argv, "error": str(exc)}
    value = (cp.stdout or cp.stderr).strip().splitlines()
    return {
        "present": True,
        "value": value[0].strip() if value else None,
        "command": argv,
        "returnCode": cp.returncode,
    }


def _toolchain() -> dict[str, Any]:
    probes = {
        "node": _run_version(["node", "--version"]),
        "npm": _run_version(["npm", "--version"]),
        "python": _run_version(["python", "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"]),
        "uv": _run_version(["uv", "--version"]),
    }
    if probes["uv"].get("value", "").startswith("uv "):
        probes["uv"]["value"] = probes["uv"]["value"].split(maxsplit=1)[1]
    for name, expected in EXPECTED.items():
        probes[name]["expected"] = expected
        probes[name]["matchesExpected"] = probes[name].get("value") == expected
    return probes


def _network() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(4.0)
    try:
        for host, port, purpose in NETWORK_TARGETS:
            item: dict[str, Any] = {"host": host, "port": port, "purpose": purpose}
            try:
                infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
                addresses = sorted({entry[4][0] for entry in infos})
                item["dnsResolved"] = True
                item["addresses"] = addresses[:8]
            except OSError as exc:
                item.update({"dnsResolved": False, "tcpReachable": False, "error": str(exc)})
                results.append(item)
                continue
            try:
                with socket.create_connection((host, port), timeout=4.0):
                    pass
                item["tcpReachable"] = True
            except OSError as exc:
                item.update({"tcpReachable": False, "error": str(exc)})
            results.append(item)
    finally:
        socket.setdefaulttimeout(old_timeout)
    return results


def _path_state(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "isFile": path.is_file(),
        "isDirectory": path.is_dir(),
        "isSymlink": path.is_symlink(),
        "bytes": path.stat().st_size if path.is_file() else None,
    }


def _repo_state(repo: Path) -> dict[str, Any]:
    return {
        "packageLock": _path_state(repo / "package-lock.json"),
        "uvLock": _path_state(repo / "engine" / "uv.lock"),
        "sourceIntegrityManifest": _path_state(repo / "SOURCE_SHA256SUMS.txt"),
        "productionFreeze": _path_state(repo / "engine" / "mte_engine" / "benchmark" / "production-profile-freeze.json"),
    }


def _input_state(root: Path | None, bundle_relative: str | None) -> dict[str, Any]:
    if root is None:
        return {"configured": False, "bundle": {"configured": False}}
    state: dict[str, Any] = {"configured": True, "root": _path_state(root)}
    if not root.is_dir() or root.is_symlink():
        state["bundle"] = {"configured": bool(bundle_relative), "valid": False, "error": "qualification input root is not a real directory"}
        return state
    candidates = {
        "corpusCandidates": list(root.rglob("*corpus*.json")),
        "artifactReviewCandidates": list(root.rglob("*.review.json")),
        "manualOnnxPackages": list(root.rglob("*.zip")),
        "benchmarkReviewCandidates": list(root.rglob("*benchmark*review*.json")),
        "preparedRunPlans": list(root.rglob("benchmark-run-plan.json")),
    }
    for key, paths in candidates.items():
        safe = [p for p in paths if p.is_file() and not p.is_symlink()]
        state[key] = {"count": len(safe), "paths": [str(p) for p in safe[:30]]}
    if bundle_relative:
        try:
            bundle_path = resolve_below(root.resolve(strict=True), bundle_relative, label="readiness qualification input bundle", kind="file")
            verified = verify_qualification_input_bundle(root.resolve(strict=True), bundle_path, verify_semantics=True)
            state["bundle"] = {
                "configured": True,
                "path": str(bundle_path),
                "valid": True,
                "bundleSha256": str(verified["bundleSha256"]),
                "corpus": str(verified["corpus"]),
                "reviewsDir": str(verified["reviewsDir"]),
                "manualArtifactsDir": str(verified["manualArtifactsDir"]),
            }
        except (QualificationBundleError, OSError, ValueError) as exc:
            state["bundle"] = {"configured": True, "valid": False, "error": str(exc)}
    else:
        state["bundle"] = {"configured": False, "valid": False, "error": "sealed REV13 input bundle path is required"}
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed readiness probe for the real production qualification environment.")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--input-bundle", default="qualification-input-bundle.json", help="Sealed REV13 input bundle path relative to --input-root.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict", action="store_true", help="Return non-zero unless pinned toolchain, network and an input root are available.")
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    input_root = args.input_root.absolute() if args.input_root else None
    toolchain = _toolchain()
    network = _network()
    inputs = _input_state(input_root, args.input_bundle if input_root else None)
    repo_state = _repo_state(repo)

    blockers: list[str] = []
    for name, item in toolchain.items():
        if not item.get("matchesExpected"):
            blockers.append(f"toolchain:{name}")
    for item in network:
        if not item.get("dnsResolved") or not item.get("tcpReachable"):
            blockers.append(f"network:{item['purpose']}")
    if input_root is None or not input_root.is_dir() or input_root.is_symlink():
        blockers.append("operator-input-root")
    elif not inputs.get("bundle", {}).get("valid"):
        blockers.append("operator-input-bundle")

    report = {
        "schemaVersion": 1,
        "revision": "rev13-real-qualification-readiness-v2-sealed-input-bundle",
        "generatedAtUtc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "classification": "diagnostic-only-not-release-evidence",
        "repoRoot": str(repo),
        "toolchain": toolchain,
        "network": network,
        "repositoryEvidence": repo_state,
        "operatorInputs": inputs,
        "readyForRealQualification": not blockers,
        "blockers": blockers,
        "safety": {
            "createsProductionFreeze": False,
            "downloadsModelArtifacts": False,
            "modifiesOperatorInputs": False,
        },
    }
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 2 if args.strict and blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
