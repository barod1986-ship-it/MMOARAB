from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

from .acquisition import load_source_registry, source_for_artifact
from .candidate_plan import load_candidate_plan, plan_artifact_ids
from .catalog import artifact_by_id, load_catalog
from .common import canonical_json, is_sha256, sha256_bytes, sha256_file
from .corpus import load_corpus, production_corpus_gate, validate_corpus
from .gate import load_policy
from .manual_artifacts import inspect_inpaint_package, load_manual_policy

ENGINE_ROOT = Path(__file__).resolve().parents[2]
ACTIVE_CATALOG = ENGINE_ROOT / "model-catalog" / "model-candidates-v1.json"
ACTIVE_SOURCE_REGISTRY = ENGINE_ROOT / "model-catalog" / "acquisition-source-registry-v3.json"
ACTIVE_MANUAL_POLICY = ENGINE_ROOT / "model-catalog" / "manual-derived-artifact-policy-v1.json"
ACTIVE_POLICY = ENGINE_ROOT / "benchmark" / "policies" / "benchmark-thresholds-v3.json"
ACTIVE_CANDIDATE_PLAN = ENGINE_ROOT / "benchmark" / "candidate-plan-v3.json"
BUNDLE_SCHEMA_VERSION = 1
BUNDLE_REVISION = "rev13-production-qualification-input-bundle-v1"
AUTOMATED_MODES = {"direct-https-file", "https-tree", "https-zip-member"}
EXPECTED_AUTOMATED = {
    "ppocrv6-small-det",
    "ppocrv6-medium-det",
    "ppocrv6-small-rec",
    "ppocrv6-medium-rec",
    "ppocrv5-korean-mobile-rec",
    "manga-ocr-base-0.1.16",
    "noto-sans-arabic-production-font",
}
EXPECTED_MANUAL = {"lama-big", "aot-gan-places2"}
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
ALLOWED_ACQUISITION_METHODS = {"manual-download", "official-cli", "local-conversion", "local-copy"}

CONTROL_FILES = {
    "catalog": ACTIVE_CATALOG,
    "sourceRegistry": ACTIVE_SOURCE_REGISTRY,
    "manualArtifactPolicy": ACTIVE_MANUAL_POLICY,
    "benchmarkPolicy": ACTIVE_POLICY,
    "candidatePlan": ACTIVE_CANDIDATE_PLAN,
}


class QualificationBundleError(ValueError):
    pass


def _fail(message: str) -> None:
    raise QualificationBundleError(message)


def safe_relative(value: str, *, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\n" in value or "\r" in value:
        _fail(f"{label} must be a non-empty relative POSIX path without control characters")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        _fail(f"{label} must remain below the qualification input root")
    return path


def resolve_below(root: Path, value: str, *, label: str, kind: str, may_not_exist: bool = False) -> Path:
    root = root.resolve(strict=True)
    relative = safe_relative(value, label=label)
    target = root.joinpath(*relative.parts)
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.exists() and cursor.is_symlink():
            _fail(f"{label} contains a symlink component: {cursor}")
    resolved = target.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        _fail(f"{label} escapes the qualification input root")
    if not may_not_exist or resolved.exists():
        if kind == "file" and (not resolved.is_file() or resolved.is_symlink()):
            _fail(f"{label} must be a regular file")
        if kind == "dir" and (not resolved.is_dir() or resolved.is_symlink()):
            _fail(f"{label} must be a real directory")
    return resolved


def _active_topology() -> tuple[list[str], set[str], set[str], dict[str, dict[str, Any]]]:
    catalog = load_catalog(ACTIVE_CATALOG)
    policy = load_policy(ACTIVE_POLICY)
    plan = load_candidate_plan(ACTIVE_CANDIDATE_PLAN, catalog=catalog, policy=policy)
    ids = plan_artifact_ids(plan)
    by_id = artifact_by_id(catalog)
    registry = load_source_registry(ACTIVE_SOURCE_REGISTRY)
    automated = {artifact_id for artifact_id in ids if str(source_for_artifact(registry, artifact_id)["mode"]) in AUTOMATED_MODES}
    manual = set(ids) - automated
    if automated != EXPECTED_AUTOMATED or manual != EXPECTED_MANUAL:
        _fail("active V1 qualification topology is not exactly seven automated artifacts plus LaMa/AOT")
    return ids, automated, manual, by_id


def validate_artifact_review(path: Path, artifact_id: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        _fail(f"missing reviewed artifact decision: {artifact_id}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"cannot read artifact review for {artifact_id}: {exc}")
    if not isinstance(value, dict) or value.get("schemaVersion") != 1 or value.get("artifactId") != artifact_id:
        _fail(f"artifact review schema/artifactId mismatch: {artifact_id}")
    for key in ("reviewRecordId", "reviewer", "reviewedAtUtc", "retrievalUrl", "acquisitionMethod"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            _fail(f"artifact review {artifact_id} is missing {key}")
    reviewed_at = str(value["reviewedAtUtc"])
    if not UTC_RE.fullmatch(reviewed_at):
        _fail(f"artifact review timestamp must be ISO-8601 UTC ending in Z: {artifact_id}")
    try:
        datetime.fromisoformat(reviewed_at[:-1] + "+00:00")
    except ValueError:
        _fail(f"artifact review timestamp is invalid: {artifact_id}")
    retrieval = urlparse(str(value["retrievalUrl"]))
    if retrieval.scheme != "https" or not retrieval.hostname or retrieval.username or retrieval.password:
        _fail(f"artifact review retrievalUrl must be credential-free HTTPS: {artifact_id}")
    if value.get("acquisitionMethod") not in ALLOWED_ACQUISITION_METHODS:
        _fail(f"artifact review acquisitionMethod is invalid: {artifact_id}")
    if value.get("benchmarkUseStatus") != "approved":
        _fail(f"benchmark use must be approved before bundle sealing: {artifact_id}")
    if value.get("artifactLicenseStatus") != "approved":
        _fail(f"artifact license must be approved before bundle sealing: {artifact_id}")
    if value.get("redistributionStatus") not in {"approved", "local-only"}:
        _fail(f"artifact redistribution decision is not final: {artifact_id}")
    evidence = value.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        _fail(f"artifact review evidence is required: {artifact_id}")
    for index, item in enumerate(evidence):
        if not isinstance(item, dict) or not isinstance(item.get("kind"), str) or not item["kind"].strip():
            _fail(f"artifact review evidence kind is required: {artifact_id}[{index}]")
        evidence_url = urlparse(str(item.get("url", "")))
        if evidence_url.scheme != "https" or not evidence_url.hostname or evidence_url.username or evidence_url.password:
            _fail(f"artifact review evidence URL must be credential-free HTTPS: {artifact_id}[{index}]")
    return value


def _control_pins() -> dict[str, str]:
    return {name: sha256_file(path) for name, path in CONTROL_FILES.items()}


def _bundle_digest(value: dict[str, Any]) -> str:
    material = dict(value)
    material.pop("bundleSha256", None)
    return sha256_bytes(canonical_json(material))


def _semantic_snapshot(root: Path, *, corpus_relative: str, reviews_relative: str, manual_relative: str) -> dict[str, Any]:
    corpus_path = resolve_below(root, corpus_relative, label="corpus", kind="file")
    reviews_dir = resolve_below(root, reviews_relative, label="artifact reviews directory", kind="dir")
    manual_dir = resolve_below(root, manual_relative, label="manual artifacts directory", kind="dir")

    corpus = load_corpus(corpus_path, verify_files=True)
    corpus_summary = validate_corpus(corpus, base_dir=corpus_path.parent, verify_files=True)
    corpus_ok, reasons = production_corpus_gate(corpus_summary)
    if not corpus_ok:
        _fail("production corpus gate failed: " + "; ".join(reasons))

    artifact_ids, automated, manual, by_id = _active_topology()
    reviews: list[dict[str, str]] = []
    for artifact_id in artifact_ids:
        review_path = reviews_dir / f"{artifact_id}.review.json"
        validate_artifact_review(review_path, artifact_id)
        reviews.append({
            "artifactId": artifact_id,
            "path": review_path.relative_to(root).as_posix(),
            "sha256": sha256_file(review_path),
        })

    manual_policy = load_manual_policy(ACTIVE_MANUAL_POLICY)
    manual_items: list[dict[str, str]] = []
    for artifact_id in sorted(manual):
        expected_filename = str(by_id[artifact_id]["expectedFilename"])
        package = manual_dir / expected_filename
        if package.is_symlink() or not package.is_file():
            _fail(f"reviewed manual artifact is missing: {artifact_id}")
        policy_item = manual_policy["artifacts"].get(artifact_id)
        if not isinstance(policy_item, dict):
            _fail(f"manual artifact policy is missing: {artifact_id}")
        inspected = inspect_inpaint_package(package, artifact_id=artifact_id, expected_candidate_id=str(policy_item["candidateId"]))
        manual_items.append({
            "artifactId": artifact_id,
            "path": package.relative_to(root).as_posix(),
            "sha256": str(inspected["packageSha256"]),
        })

    return {
        "corpus": {
            "corpusId": str(corpus["corpusId"]),
            "path": corpus_path.relative_to(root).as_posix(),
            "sha256": sha256_file(corpus_path),
            "pageCount": int(corpus_summary["pageCount"]),
        },
        "reviewsDir": reviews_dir.relative_to(root).as_posix(),
        "artifactReviews": reviews,
        "manualArtifactsDir": manual_dir.relative_to(root).as_posix(),
        "manualArtifacts": manual_items,
        "topology": {
            "automatedArtifactCount": len(automated),
            "manualArtifactCount": len(manual),
            "artifactIds": artifact_ids,
        },
        "controlPins": _control_pins(),
    }


def seal_qualification_input_bundle(root: Path, *, corpus_relative: str, reviews_relative: str, manual_relative: str) -> dict[str, Any]:
    root = root.resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        _fail("qualification input root must be a real directory")
    snapshot = _semantic_snapshot(
        root,
        corpus_relative=corpus_relative,
        reviews_relative=reviews_relative,
        manual_relative=manual_relative,
    )
    bundle: dict[str, Any] = {
        "schemaVersion": BUNDLE_SCHEMA_VERSION,
        "bundleRevision": BUNDLE_REVISION,
        "sealedAtUtc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "classification": "operator-input-binding-not-release-approval",
        **snapshot,
    }
    bundle["bundleSha256"] = _bundle_digest(bundle)
    return bundle


def _expect_pin(value: object, expected: str, *, label: str) -> None:
    if not is_sha256(value) or value != expected:
        _fail(f"qualification input bundle digest mismatch: {label}")


def verify_qualification_input_bundle(root: Path, bundle_path: Path, *, verify_semantics: bool = True) -> dict[str, Any]:
    root = root.resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        _fail("qualification input root must be a real directory")
    if bundle_path.is_symlink() or not bundle_path.is_file():
        _fail("qualification input bundle must be a regular file")
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"cannot read qualification input bundle: {exc}")
    if not isinstance(bundle, dict) or bundle.get("schemaVersion") != BUNDLE_SCHEMA_VERSION or bundle.get("bundleRevision") != BUNDLE_REVISION:
        _fail("qualification input bundle schema/revision mismatch")
    if bundle.get("classification") != "operator-input-binding-not-release-approval":
        _fail("qualification input bundle classification mismatch")
    digest = bundle.get("bundleSha256")
    if not is_sha256(digest) or digest != _bundle_digest(bundle):
        _fail("qualification input bundle self-digest mismatch")

    corpus = bundle.get("corpus")
    if not isinstance(corpus, dict):
        _fail("qualification input bundle corpus entry is missing")
    reviews_dir = bundle.get("reviewsDir")
    manual_dir = bundle.get("manualArtifactsDir")
    if not isinstance(reviews_dir, str) or not isinstance(manual_dir, str):
        _fail("qualification input bundle review/manual directories are missing")
    corpus_path = resolve_below(root, str(corpus.get("path", "")), label="bundle corpus", kind="file")
    resolved_reviews = resolve_below(root, reviews_dir, label="bundle reviews directory", kind="dir")
    resolved_manual = resolve_below(root, manual_dir, label="bundle manual directory", kind="dir")
    _expect_pin(corpus.get("sha256"), sha256_file(corpus_path), label="corpus")

    artifact_ids, automated, manual, by_id = _active_topology()
    topology = bundle.get("topology")
    if not isinstance(topology, dict) or topology.get("artifactIds") != artifact_ids or topology.get("automatedArtifactCount") != len(automated) or topology.get("manualArtifactCount") != len(manual):
        _fail("qualification input bundle topology mismatch")

    review_entries = bundle.get("artifactReviews")
    if not isinstance(review_entries, list) or len(review_entries) != len(artifact_ids):
        _fail("qualification input bundle must pin exactly one review per active artifact")
    by_review_id: dict[str, dict[str, Any]] = {}
    for entry in review_entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("artifactId"), str):
            _fail("qualification input bundle contains an invalid artifact review entry")
        artifact_id = str(entry["artifactId"])
        if artifact_id in by_review_id:
            _fail(f"qualification input bundle duplicates review: {artifact_id}")
        by_review_id[artifact_id] = entry
    if set(by_review_id) != set(artifact_ids):
        _fail("qualification input bundle artifact review set does not match the active plan")
    for artifact_id in artifact_ids:
        entry = by_review_id[artifact_id]
        expected_path = resolved_reviews / f"{artifact_id}.review.json"
        actual_path = resolve_below(root, str(entry.get("path", "")), label=f"bundle review {artifact_id}", kind="file")
        if actual_path != expected_path:
            _fail(f"qualification input bundle review path is not canonical: {artifact_id}")
        _expect_pin(entry.get("sha256"), sha256_file(actual_path), label=f"review:{artifact_id}")

    manual_entries = bundle.get("manualArtifacts")
    if not isinstance(manual_entries, list) or len(manual_entries) != len(manual):
        _fail("qualification input bundle must pin exactly LaMa and AOT packages")
    by_manual_id: dict[str, dict[str, Any]] = {}
    for entry in manual_entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("artifactId"), str):
            _fail("qualification input bundle contains an invalid manual artifact entry")
        artifact_id = str(entry["artifactId"])
        if artifact_id in by_manual_id:
            _fail(f"qualification input bundle duplicates manual artifact: {artifact_id}")
        by_manual_id[artifact_id] = entry
    if set(by_manual_id) != manual:
        _fail("qualification input bundle manual artifact set must be exactly LaMa/AOT")
    for artifact_id in sorted(manual):
        entry = by_manual_id[artifact_id]
        expected_path = resolved_manual / str(by_id[artifact_id]["expectedFilename"])
        actual_path = resolve_below(root, str(entry.get("path", "")), label=f"bundle manual artifact {artifact_id}", kind="file")
        if actual_path != expected_path:
            _fail(f"qualification input bundle manual artifact path is not canonical: {artifact_id}")
        _expect_pin(entry.get("sha256"), sha256_file(actual_path), label=f"manual:{artifact_id}")

    pins = bundle.get("controlPins")
    expected_pins = _control_pins()
    if not isinstance(pins, dict) or set(pins) != set(expected_pins):
        _fail("qualification input bundle control pin set mismatch")
    for name, expected in expected_pins.items():
        _expect_pin(pins.get(name), expected, label=f"control:{name}")

    if verify_semantics:
        snapshot = _semantic_snapshot(root, corpus_relative=str(corpus["path"]), reviews_relative=reviews_dir, manual_relative=manual_dir)
        if snapshot["corpus"]["corpusId"] != corpus.get("corpusId") or snapshot["corpus"]["pageCount"] != corpus.get("pageCount"):
            _fail("qualification input bundle corpus semantic summary mismatch")
        # Semantic validation above re-opens every review and both manual packages and re-runs the production corpus gate.

    return {
        "bundle": bundle,
        "bundleSha256": digest,
        "corpus": corpus_path,
        "reviewsDir": resolved_reviews,
        "manualArtifactsDir": resolved_manual,
    }
