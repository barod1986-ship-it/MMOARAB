from __future__ import annotations

import json
from pathlib import Path

import pytest

from mte_engine.benchmark import qualification_bundle as qb


def _fake_bundle_root(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "qualification-inputs"
    root.mkdir()
    corpus = root / "corpus" / "corpus.json"
    corpus.parent.mkdir()
    corpus.write_text("{}\n", encoding="utf-8")
    reviews = root / "reviews"
    reviews.mkdir()
    manual = root / "manual"
    manual.mkdir()

    artifact_ids, automated, manual_ids, by_id = qb._active_topology()
    review_entries = []
    for artifact_id in artifact_ids:
        path = reviews / f"{artifact_id}.review.json"
        path.write_text(json.dumps({"artifactId": artifact_id}) + "\n", encoding="utf-8")
        review_entries.append({"artifactId": artifact_id, "path": path.relative_to(root).as_posix(), "sha256": qb.sha256_file(path)})
    manual_entries = []
    for artifact_id in sorted(manual_ids):
        path = manual / str(by_id[artifact_id]["expectedFilename"])
        path.write_bytes((artifact_id + "\n").encode())
        manual_entries.append({"artifactId": artifact_id, "path": path.relative_to(root).as_posix(), "sha256": qb.sha256_file(path)})

    bundle = {
        "schemaVersion": qb.BUNDLE_SCHEMA_VERSION,
        "bundleRevision": qb.BUNDLE_REVISION,
        "sealedAtUtc": "2026-08-19T00:00:00Z",
        "classification": "operator-input-binding-not-release-approval",
        "corpus": {"corpusId": "test", "path": corpus.relative_to(root).as_posix(), "sha256": qb.sha256_file(corpus), "pageCount": 1},
        "reviewsDir": reviews.relative_to(root).as_posix(),
        "artifactReviews": review_entries,
        "manualArtifactsDir": manual.relative_to(root).as_posix(),
        "manualArtifacts": manual_entries,
        "topology": {"automatedArtifactCount": len(automated), "manualArtifactCount": len(manual_ids), "artifactIds": artifact_ids},
        "controlPins": qb._control_pins(),
    }
    bundle["bundleSha256"] = qb._bundle_digest(bundle)
    bundle_path = root / "qualification-input-bundle.json"
    bundle_path.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    return root, bundle_path


def test_structural_bundle_verification_binds_all_expected_inputs(tmp_path: Path):
    root, bundle_path = _fake_bundle_root(tmp_path)
    result = qb.verify_qualification_input_bundle(root, bundle_path, verify_semantics=False)
    assert result["bundleSha256"].startswith("sha256:")
    assert result["reviewsDir"] == (root / "reviews").resolve()
    assert result["manualArtifactsDir"] == (root / "manual").resolve()


def test_bundle_rejects_changed_input_bytes(tmp_path: Path):
    root, bundle_path = _fake_bundle_root(tmp_path)
    (root / "corpus" / "corpus.json").write_text('{"changed":true}\n', encoding="utf-8")
    with pytest.raises(qb.QualificationBundleError, match="digest mismatch: corpus"):
        qb.verify_qualification_input_bundle(root, bundle_path, verify_semantics=False)


def test_bundle_rejects_path_escape_even_with_resealed_self_digest(tmp_path: Path):
    root, bundle_path = _fake_bundle_root(tmp_path)
    value = json.loads(bundle_path.read_text(encoding="utf-8"))
    value["corpus"]["path"] = "../outside.json"
    value["bundleSha256"] = qb._bundle_digest(value)
    bundle_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
    with pytest.raises(qb.QualificationBundleError, match="remain below"):
        qb.verify_qualification_input_bundle(root, bundle_path, verify_semantics=False)


def test_bundle_rejects_duplicate_review_binding(tmp_path: Path):
    root, bundle_path = _fake_bundle_root(tmp_path)
    value = json.loads(bundle_path.read_text(encoding="utf-8"))
    value["artifactReviews"][1]["artifactId"] = value["artifactReviews"][0]["artifactId"]
    value["bundleSha256"] = qb._bundle_digest(value)
    bundle_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
    with pytest.raises(qb.QualificationBundleError, match="duplicates review"):
        qb.verify_qualification_input_bundle(root, bundle_path, verify_semantics=False)


def test_safe_relative_rejects_windows_and_parent_paths():
    with pytest.raises(qb.QualificationBundleError):
        qb.safe_relative("..\\outside", label="test")
    with pytest.raises(qb.QualificationBundleError):
        qb.safe_relative("../outside", label="test")


def test_review_semantics_reject_invalid_timestamp_before_acquisition(tmp_path: Path):
    review = tmp_path / "ppocrv6-small-det.review.json"
    review.write_text(json.dumps({
        "schemaVersion": 1,
        "artifactId": "ppocrv6-small-det",
        "reviewRecordId": "review-1",
        "reviewer": "reviewer",
        "reviewedAtUtc": "not-a-time",
        "benchmarkUseStatus": "approved",
        "artifactLicenseStatus": "approved",
        "redistributionStatus": "local-only",
        "retrievalUrl": "https://example.com/model.tar",
        "acquisitionMethod": "official-cli",
        "evidence": [{"kind": "license", "url": "https://example.com/license"}],
    }) + "\n", encoding="utf-8")
    with pytest.raises(qb.QualificationBundleError, match="timestamp"):
        qb.validate_artifact_review(review, "ppocrv6-small-det")


def test_review_semantics_reject_non_https_evidence_before_acquisition(tmp_path: Path):
    review = tmp_path / "ppocrv6-small-det.review.json"
    review.write_text(json.dumps({
        "schemaVersion": 1,
        "artifactId": "ppocrv6-small-det",
        "reviewRecordId": "review-1",
        "reviewer": "reviewer",
        "reviewedAtUtc": "2026-08-19T00:00:00Z",
        "benchmarkUseStatus": "approved",
        "artifactLicenseStatus": "approved",
        "redistributionStatus": "local-only",
        "retrievalUrl": "https://example.com/model.tar",
        "acquisitionMethod": "official-cli",
        "evidence": [{"kind": "license", "url": "http://example.com/license"}],
    }) + "\n", encoding="utf-8")
    with pytest.raises(qb.QualificationBundleError, match="credential-free HTTPS"):
        qb.validate_artifact_review(review, "ppocrv6-small-det")
