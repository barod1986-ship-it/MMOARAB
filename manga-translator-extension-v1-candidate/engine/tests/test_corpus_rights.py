from __future__ import annotations

import json
from pathlib import Path

import pytest

from mte_engine.benchmark.common import sha256_path
from mte_engine.benchmark.corpus import production_corpus_gate
from mte_engine.benchmark.corpus_sources import CorpusSourceError, load_source_registry, validate_page_rights


def _write_review(root: Path, *, source_id: str, source_revision: str, page_ids: list[str], commercial: bool = True, redistribution: bool = False) -> tuple[str, str]:
    path = root / "rights" / "review.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {
        "schemaVersion": 1,
        "reviewRecordId": "review-1",
        "sourceId": source_id,
        "sourceRevision": source_revision,
        "reviewer": "unit-test",
        "reviewedAtUtc": "2026-08-19T12:00:00Z",
        "benchmarkUseAuthorized": True,
        "commercialV1QualificationAuthorized": commercial,
        "redistributionAuthorized": redistribution,
        "coverageMode": "page-list",
        "pageIds": page_ids,
        "evidence": [{"kind": "permission-record", "ref": "internal:rights/review-1"}],
    }
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path.relative_to(root).as_posix(), sha256_path(path)


def _rights(*, review_path: str, review_sha: str, source_id: str = "operator-owned-or-explicitly-permissioned", source_revision: str = "owned-fixture-v1") -> dict:
    return {
        "sourceId": source_id,
        "sourceRevision": source_revision,
        "reviewRecordPath": review_path,
        "reviewRecordSha256": review_sha,
        "reviewRecordId": "review-1",
        "reviewedBy": "unit-test",
        "reviewedAtUtc": "2026-08-19T12:00:00Z",
        "redistributionAuthorized": False,
    }


def test_operator_rights_review_is_content_addressed_and_page_scoped(tmp_path: Path):
    registry = load_source_registry()
    review_path, review_sha = _write_review(tmp_path, source_id="operator-owned-or-explicitly-permissioned", source_revision="owned-fixture-v1", page_ids=["p1"])
    result = validate_page_rights(page_id="p1", language="en", rights=_rights(review_path=review_path, review_sha=review_sha), base_dir=tmp_path, registry=registry, verify_files=True)
    assert result["realDomain"] is True

    with pytest.raises(CorpusSourceError, match="does not enumerate this page"):
        validate_page_rights(page_id="p2", language="en", rights=_rights(review_path=review_path, review_sha=review_sha), base_dir=tmp_path, registry=registry, verify_files=True)


def test_tampered_rights_review_is_rejected(tmp_path: Path):
    registry = load_source_registry()
    review_path, review_sha = _write_review(tmp_path, source_id="operator-owned-or-explicitly-permissioned", source_revision="owned-fixture-v1", page_ids=["p1"])
    (tmp_path / review_path).write_text("{}\n", encoding="utf-8")
    with pytest.raises(CorpusSourceError, match="rights review digest mismatch"):
        validate_page_rights(page_id="p1", language="en", rights=_rights(review_path=review_path, review_sha=review_sha), base_dir=tmp_path, registry=registry, verify_files=True)


def test_noncommercial_public_source_is_blocked_for_production_v1(tmp_path: Path):
    registry = load_source_registry()
    rights = {
        "sourceId": "open-mantra-cc-by-nc-4.0",
        "sourceRevision": "open-mantra-main-license-cc-by-nc-4.0",
        "reviewRecordPath": "rights/not-needed.json",
        "reviewRecordSha256": "sha256:" + "0" * 64,
        "reviewRecordId": "review-1",
        "reviewedBy": "unit-test",
        "reviewedAtUtc": "2026-08-19T12:00:00Z",
        "redistributionAuthorized": False,
    }
    with pytest.raises(CorpusSourceError, match="not eligible for production/commercial V1 qualification"):
        validate_page_rights(page_id="p1", language="ja", rights=rights, base_dir=tmp_path, registry=registry, verify_files=False)


def test_synthetic_pages_cannot_satisfy_real_domain_minimums():
    summary = {
        "languageCounts": {"en": 60, "ja": 10, "ko": 10, "zh-Hans": 5, "zh-Hant": 5},
        "realDomainLanguageCounts": {},
        "missingCoverageFeatures": [],
        "languageFeatures": {
            "en": ["english-uppercase-or-italic-or-outline"],
            "ja": ["vertical-japanese", "furigana"],
            "ko": [], "zh-Hans": [], "zh-Hant": [],
        },
        "groundTruthSfxPages": 10,
        "groundTruthSfxPagesByLanguage": {"en": 5, "ja": 1, "ko": 1, "zh-Hans": 1, "zh-Hant": 2},
        "cleanReferencePages": 5,
    }
    passed, reasons = production_corpus_gate(summary)
    assert passed is False
    assert any("real-domain English" in reason for reason in reasons)
    assert any("real-domain Japanese" in reason for reason in reasons)
    assert any("real-domain Korean" in reason for reason in reasons)
    assert any("real-domain Chinese" in reason for reason in reasons)
