from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "scripts"))

from mte_engine.benchmark.common import sha256_file
from mte_engine.benchmark.dependency_locks import dependency_lock_pins, validate_package_lock, validate_uv_lock
from mte_engine.benchmark.freeze import load_freeze
from mte_engine.benchmark.gate import load_policy
from mte_engine.benchmark.source_binding import verify_current_source_binding
from source_integrity import render_manifest

REVISION = "rev16-qualification-release-evidence-v1"
EXPECTED_FILES = {
    "package-lock.json",
    "uv.lock",
    "production-profile-freeze.json",
    "qualification-execution-summary.json",
    "qualification-session.json",
}


class PromotionError(ValueError):
    pass


def _regular(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file() or path.stat().st_size <= 0:
        raise PromotionError(f"{label} must be a non-empty regular file: {path}")
    return path


def _load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(_regular(path, label).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PromotionError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise PromotionError(f"{label} must contain a JSON object")
    return value


def _derive_ml_flags(root: Path, freeze: dict) -> tuple[bool, bool]:
    policy = load_policy(root / "engine" / "benchmark" / "policies" / "benchmark-thresholds-v3.json")
    role_policy = policy.get("roleSafety") if isinstance(policy.get("roleSafety"), dict) else {}
    role = freeze.get("roleSafetyQualification") if isinstance(freeze.get("roleSafetyQualification"), dict) else {}
    zero_fields = (
        "sentToTranslatorRate", "eraseInpaintMaskOverlapRate", "changedPixelRateAfterEncodeDecode",
        "uncertainDestructiveEditRate", "protectedConflictSilentOverwriteCount",
    )
    recall = role.get("roleClassifierSfxProtectedRecall")
    role_ready = (
        isinstance(role_policy.get("productionRevision"), str)
        and role.get("roleClassifierRevision") == role_policy.get("productionRevision")
        and isinstance(recall, (int, float)) and not isinstance(recall, bool)
        and float(recall) >= float(role_policy.get("sfxProtectedRecallMin", 1.0))
        and all(role.get(name) in (0, 0.0) for name in zero_fields)
        and isinstance(role.get("independentGroundTruthPages"), int)
        and not isinstance(role.get("independentGroundTruthPages"), bool)
        and role.get("independentGroundTruthPages", 0) >= 10
    )

    selected = freeze.get("selected") if isinstance(freeze.get("selected"), dict) else {}
    q = freeze.get("inpaintingQualification") if isinstance(freeze.get("inpaintingQualification"), dict) else {}
    candidate_id = selected.get("inpainter")
    artifact_id = {"lama-inpaint": "lama-big", "aot-inpaint": "aot-gan-places2"}.get(candidate_id)
    pins = freeze.get("selectedArtifacts") if isinstance(freeze.get("selectedArtifacts"), list) else []
    pin = next((item for item in pins if isinstance(item, dict) and item.get("artifactId") == artifact_id), None)
    threshold = float((policy.get("qualityThresholds") or {}).get("inpaintingHumanScoreMin", float("inf")))
    minimum_pages = int((policy.get("humanReviewThresholds") or {}).get("inpaintingPagesMin", 1))
    score = q.get("humanScore")
    inpaint_ready = (
        artifact_id is not None and q.get("candidateId") == candidate_id
        and isinstance(score, (int, float)) and not isinstance(score, bool) and float(score) >= threshold
        and q.get("humanCriticalFailures") == 0 and q.get("criticalReviewFailures") == 0
        and isinstance(q.get("pagesReviewed"), int) and not isinstance(q.get("pagesReviewed"), bool) and q.get("pagesReviewed", 0) >= minimum_pages
        and isinstance(pin, dict) and pin.get("kind") == "inpaint" and isinstance(pin.get("sha256"), str)
    )
    return role_ready, inpaint_ready


def promote(*, root: Path, evidence_dir: Path, expected_source_sha: str, replace: bool) -> dict:
    repo = root.resolve()
    evidence = evidence_dir.resolve()
    if evidence.is_symlink() or not evidence.is_dir():
        raise PromotionError("qualification release-evidence directory must be a real directory")
    manifest = _load_json(evidence / "qualification-release-evidence.json", "qualification release-evidence manifest")
    if manifest.get("schemaVersion") != 1 or manifest.get("revision") != REVISION:
        raise PromotionError("qualification release-evidence schema/revision is unsupported")
    if manifest.get("qualifiedSourceHeadSha") != expected_source_sha.lower():
        raise PromotionError("qualification evidence belongs to a different source commit")
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != EXPECTED_FILES:
        raise PromotionError("qualification release-evidence file set is incomplete or unexpected")
    for name in EXPECTED_FILES:
        path = _regular(evidence / name, name)
        if files.get(name) != sha256_file(path):
            raise PromotionError(f"qualification release-evidence digest mismatch: {name}")
    if any(manifest.get(key) is not False for key in ("containsModelBytes", "containsCorpusBytes", "containsOcrTextTrace")):
        raise PromotionError("qualification release-evidence safety declarations are not fail-closed")

    freeze = load_freeze(evidence / "production-profile-freeze.json")
    if freeze is None:
        raise PromotionError("qualification release-evidence contains an invalid production freeze")
    if freeze.get("freezeSha256") != manifest.get("freezeSha256") or freeze.get("runPlanSha256") != manifest.get("runPlanSha256"):
        raise PromotionError("qualification release-evidence manifest does not match the production freeze")
    if freeze.get("dependencyLocks") != manifest.get("dependencyLocks") or freeze.get("qualifiedSource") != manifest.get("qualifiedSource"):
        raise PromotionError("qualification release-evidence manifest does not match freeze lock/source binding")
    verify_current_source_binding(repo, freeze.get("qualifiedSource"))

    # Validate the imported lock graphs against the current source descriptors before touching the checkout.
    temp = Path(tempfile.mkdtemp(prefix=".qualification-promotion-"))
    try:
        (temp / "engine").mkdir(parents=True)
        shutil.copyfile(repo / "package.json", temp / "package.json")
        shutil.copyfile(evidence / "package-lock.json", temp / "package-lock.json")
        shutil.copyfile(repo / "engine" / "pyproject.toml", temp / "engine" / "pyproject.toml")
        shutil.copyfile(evidence / "uv.lock", temp / "engine" / "uv.lock")
        validate_package_lock(temp)
        validate_uv_lock(temp)
    finally:
        shutil.rmtree(temp, ignore_errors=True)

    destinations = {
        repo / "package-lock.json": evidence / "package-lock.json",
        repo / "engine" / "uv.lock": evidence / "uv.lock",
        repo / "engine" / "mte_engine" / "benchmark" / "production-profile-freeze.json": evidence / "production-profile-freeze.json",
    }
    existing = [path for path in destinations if path.exists()]
    if existing and not replace:
        raise PromotionError("qualification evidence targets already exist; use --replace only after explicit review")

    backup = Path(tempfile.mkdtemp(prefix=".qualification-promotion-backup-", dir=repo))
    changed: list[Path] = []
    try:
        for destination, source in destinations.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                rel = destination.relative_to(repo)
                saved = backup / rel
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(destination, saved)
            temp_target = destination.with_suffix(destination.suffix + ".promotion.tmp")
            shutil.copyfile(source, temp_target, follow_symlinks=False)
            temp_target.replace(destination)
            changed.append(destination)

        if dependency_lock_pins(repo) != freeze.get("dependencyLocks"):
            raise PromotionError("promoted lock bytes do not match production freeze dependency pins")
        promoted_freeze = load_freeze(repo / "engine" / "mte_engine" / "benchmark" / "production-profile-freeze.json")
        if promoted_freeze is None:
            raise PromotionError("promoted production freeze is invalid")
        verify_current_source_binding(repo, promoted_freeze.get("qualifiedSource"))

        role_ready, inpaint_ready = _derive_ml_flags(repo, promoted_freeze)
        if not role_ready or not inpaint_ready:
            raise PromotionError("production freeze does not satisfy active role/SFX and inpainting release thresholds")

        state_path = repo / "release-control" / "release-state.json"
        state = _load_json(state_path, "release state")
        blockers = state.setdefault("v1Blockers", {})
        if not isinstance(blockers, dict):
            raise PromotionError("release state v1Blockers must be an object")
        blockers["packageLockCommitted"] = True
        blockers["uvLockCommitted"] = True
        blockers["phase5bProductionFreezeReady"] = True
        blockers["productionRoleSfxClassifierReady"] = role_ready
        blockers["productionInpainterRuntimeReady"] = inpaint_ready
        state["qualificationEvidence"] = {
            "revision": REVISION,
            "qualifiedSourceHeadSha": manifest["qualifiedSourceHeadSha"],
            "runPlanSha256": manifest["runPlanSha256"],
            "freezeSha256": manifest["freezeSha256"],
        }
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        changed.append(state_path)

        source_manifest = repo / "SOURCE_SHA256SUMS.txt"
        source_manifest.write_text(render_manifest(repo), encoding="utf-8", newline="\n")
        changed.append(source_manifest)
        return {
            "schemaVersion": 1,
            "revision": REVISION,
            "qualifiedSourceHeadSha": manifest["qualifiedSourceHeadSha"],
            "runPlanSha256": manifest["runPlanSha256"],
            "freezeSha256": manifest["freezeSha256"],
            "promoted": [path.relative_to(repo).as_posix() for path in changed],
        }
    except Exception:
        for destination in changed:
            rel = destination.relative_to(repo)
            saved = backup / rel
            if saved.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(saved, destination)
            else:
                destination.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(backup, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote a passing production qualification evidence bundle into the exact qualified source checkout.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    payload = promote(root=args.root, evidence_dir=args.evidence_dir, expected_source_sha=args.expected_source_sha, replace=args.replace)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PromotionError, ValueError, OSError) as exc:
        raise SystemExit(f"qualification release-evidence promotion failed closed: {exc}")
