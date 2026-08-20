from __future__ import annotations

import json
import hashlib
import stat
import zipfile
from pathlib import Path

import pytest

from mte_engine.benchmark.candidate_plan import CandidatePlanError, compare_report_to_plan, load_candidate_plan
from mte_engine.benchmark.common import canonical_json, sha256_bytes, sha256_path
from mte_engine.benchmark.provenance import ProvenanceError, artifact_stats, receipt_digest, validate_receipt, verify_receipts
from mte_engine.benchmark.run_plan import RunPlanError, run_plan_digest, validate_run_plan
from mte_engine.benchmark.execution import EXECUTOR_REVISION
from mte_engine.benchmark.manual_artifacts import derivation_digest, inspect_inpaint_package, load_manual_policy, validate_onnx_runtime, ManualArtifactError, load_converter_review


def _write_derived_package(path: Path) -> dict:
    model_bytes=b"fake-onnx-bytes"
    model_sha="sha256:"+hashlib.sha256(model_bytes).hexdigest()
    derivation={
        "schemaVersion":1,"packagerRevision":"rev10-inpaint-onnx-packager-v1","artifactId":"lama-big","candidateId":"lama-inpaint",
        "runtimeContract":"mte-onnx-inpaint-contract-v1","sourceArtifactSha256":"sha256:"+"1"*64,
        "sourceReviewRecordId":"source-review-001","sourceReviewFileSha256":"sha256:"+"2"*64,
        "converterReviewRecordId":"converter-review-001","converterReviewFileSha256":"sha256:"+"4"*64,
        "converterRevision":"converter-commit-abc","converterSourceUrl":"https://example.invalid/converter",
        "converterSourceSha256":"sha256:"+"3"*64,"modelSha256":model_sha,"createdAtUtc":"2026-08-19T12:00:00Z",
        "operator":"unit-test","runtimeValidation":{"validatedProvider":"CPUExecutionProvider","smokeShapes":[[1,3,64,80],[1,3,96,112]]},
    }
    derivation["derivationSha256"]=derivation_digest(derivation)
    derivation_bytes=canonical_json(derivation)
    contract={
        "schemaVersion":1,"contract":"mte-onnx-inpaint-contract-v1","candidateId":"lama-inpaint","modelFile":"model.onnx",
        "imageInput":"image","maskInput":"mask","output":"output","tensorLayout":"NCHW","imageRange":"0..1-rgb","maskSemantics":"1=erase","padMultiple":8,
        "modelSha256":model_sha,"derivationManifest":"mte-derivation.json","derivationManifestSha256":"sha256:"+hashlib.sha256(derivation_bytes).hexdigest(),
    }
    with zipfile.ZipFile(path,"w") as zf:
        for name,data in [("model.onnx",model_bytes),("mte-inpaint-contract.json",canonical_json(contract)),("mte-derivation.json",derivation_bytes)]:
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0)); info.create_system=3; info.external_attr=(stat.S_IFREG|0o644)<<16
            zf.writestr(info,data)
    return derivation


def _catalog(tmp_path: Path, *, derived: bool = False) -> tuple[dict, Path]:
    artifacts = tmp_path / "models"
    artifacts.mkdir()
    if derived:
        path=artifacts/"mte-lama-big-onnx-v1.zip"; _write_derived_package(path); artifact_id="lama-big"; expected=path.name
    else:
        path=artifacts/"model.bin"; path.write_bytes(b"production-model-bytes"); artifact_id="model-a"; expected=path.name
    item = {
        "artifactId": artifact_id,
        "kind": "inpaint" if derived else "ocr",
        "upstreamProject": "owned-test",
        "upstreamRevision": "rev-a",
        "sourceUrl": "https://example.invalid/model-a",
        "expectedFilename": expected,
        "sha256": sha256_path(path),
        "codeLicense": "Apache-2.0",
        "artifactLicenseStatus": "approved",
        "redistributionStatus": "local-only",
        "benchmarkUseStatus": "approved",
        "provenanceNotes": "test",
    }
    if derived:
        item["runtimeContract"] = "mte-onnx-inpaint-contract-v1"
    return {"schemaVersion": 1, "catalogRevision": "catalog-test-v1", "artifacts": [item]}, artifacts


def _receipt(catalog: dict, artifacts: Path, *, derived: bool = False) -> dict:
    item = catalog["artifacts"][0]
    path = artifacts / item["expectedFilename"]
    size, count = artifact_stats(path)
    receipt = {
        "schemaVersion": 1,
        "receiptId": f"{item['artifactId']}-receipt",
        "artifactId": item["artifactId"],
        "catalogRevision": catalog["catalogRevision"],
        "expectedFilename": item["expectedFilename"],
        "artifactSha256": item["sha256"],
        "artifactByteSize": size,
        "artifactFileCount": count,
        "source": {
            "provenanceUrl": item["sourceUrl"],
            "retrievalUrl": "https://example.invalid/model-a/bytes",
            "upstreamRevision": item["upstreamRevision"],
            "acquisitionMethod": "local-conversion" if derived else "manual-download",
            "acquiredAtUtc": "2026-08-19T12:00:00Z",
        },
        "review": {
            "reviewed": True,
            "reviewRecordId": "review-001",
            "reviewer": "unit-test-reviewer",
            "reviewedAtUtc": "2026-08-19T12:05:00Z",
            "benchmarkUseStatus": "approved",
            "artifactLicenseStatus": "approved",
            "redistributionStatus": "local-only",
            "evidence": [{"kind": "license", "url": "https://example.invalid/license"}],
        },
    }
    if derived:
        d=inspect_inpaint_package(path,artifact_id="lama-big",expected_candidate_id="lama-inpaint")["derivation"]
        receipt["derivation"]={k:d[k] for k in ["runtimeContract","packagerRevision","sourceArtifactSha256","sourceReviewRecordId","sourceReviewFileSha256","converterReviewRecordId","converterReviewFileSha256","converterRevision","converterSourceUrl","converterSourceSha256","modelSha256","derivationSha256"]}
    receipt["receiptSha256"] = receipt_digest(receipt)
    return receipt


def test_artifact_receipt_binds_local_bytes_catalog_and_review(tmp_path: Path):
    catalog, artifacts = _catalog(tmp_path)
    receipt = _receipt(catalog, artifacts)
    validate_receipt(receipt, catalog=catalog, artifacts_dir=artifacts)
    receipt["review"]["reviewer"] = "tampered"
    with pytest.raises(ProvenanceError, match="content digest mismatch"):
        validate_receipt(receipt, catalog=catalog, artifacts_dir=artifacts)


def test_derived_runtime_artifact_requires_conversion_provenance(tmp_path: Path):
    catalog, artifacts = _catalog(tmp_path, derived=True)
    receipt = _receipt(catalog, artifacts, derived=False)
    with pytest.raises(ProvenanceError, match="requires derivation provenance"):
        validate_receipt(receipt, catalog=catalog, artifacts_dir=artifacts)
    receipt = _receipt(catalog, artifacts, derived=True)
    validate_receipt(receipt, catalog=catalog, artifacts_dir=artifacts)


def test_derived_package_contract_binds_model_and_derivation_bytes(tmp_path: Path):
    package=tmp_path/"mte-lama-big-onnx-v1.zip"; _write_derived_package(package)
    inspected=inspect_inpaint_package(package,artifact_id="lama-big",expected_candidate_id="lama-inpaint")
    assert inspected["modelSha256"].startswith("sha256:")
    # Replace only model bytes while retaining old contract/derivation pins.
    with zipfile.ZipFile(package,"r") as src:
        contract=src.read("mte-inpaint-contract.json"); deriv=src.read("mte-derivation.json")
    with zipfile.ZipFile(package,"w") as zf:
        zf.writestr("model.onnx",b"tampered"); zf.writestr("mte-inpaint-contract.json",contract); zf.writestr("mte-derivation.json",deriv)
    with pytest.raises(ManualArtifactError,match="model SHA-256 mismatch"):
        inspect_inpaint_package(package,artifact_id="lama-big",expected_candidate_id="lama-inpaint")


def test_manual_policy_onnx_runtime_validation_requires_dynamic_smoke_success(tmp_path: Path):
    root=Path(__file__).resolve().parents[2]
    policy=load_manual_policy(root/"engine/model-catalog/manual-derived-artifact-policy-v1.json")
    model=tmp_path/"model.onnx"; model.write_bytes(b"fake")
    class Meta:
        def __init__(self,name): self.name=name
    class Session:
        def get_inputs(self): return [Meta("image"),Meta("mask")]
        def get_outputs(self): return [Meta("output")]
        def run(self, outputs, feeds): return [feeds["image"].copy()]
    result=validate_onnx_runtime(model,policy["artifacts"]["lama-big"],session_factory=lambda path,providers:Session())
    assert len(result["smokeShapes"])==2


def test_receipt_verifier_fails_closed_on_missing_receipt(tmp_path: Path):
    catalog, artifacts = _catalog(tmp_path)
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    passed, reasons, values = verify_receipts(catalog, ["model-a"], receipts_dir=receipts, artifacts_dir=artifacts)
    assert not passed and not values
    assert reasons == ["artifact provenance receipt is missing: model-a"]


def test_candidate_plan_exactly_binds_report_artifact_mapping(tmp_path: Path):
    catalog, _ = _catalog(tmp_path)
    policy = {"candidateCoverage": {"ocr-en": ["family-a"]}}
    plan = {
        "schemaVersion": 1,
        "planRevision": "plan-v1",
        "candidates": [{"candidateId": "ocr-a", "component": "ocr-en", "family": "family-a", "artifactIds": ["model-a"]}],
        "supportArtifactIds": [],
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    loaded = load_candidate_plan(path, catalog=catalog, policy=policy)
    report = {"candidates": [{**loaded["candidates"][0], "metrics": {"cer": 0.1}}]}
    assert compare_report_to_plan(report, loaded) == []
    report["candidates"][0]["artifactIds"] = ["other-model"]
    assert compare_report_to_plan(report, loaded)


def test_candidate_plan_cannot_drop_policy_family(tmp_path: Path):
    catalog, _ = _catalog(tmp_path)
    plan = {"schemaVersion": 1, "planRevision": "plan-v1", "candidates": [{"candidateId": "ocr-a", "component": "ocr-en", "family": "family-a", "artifactIds": ["model-a"]}], "supportArtifactIds": []}
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(CandidatePlanError, match="misses required"):
        load_candidate_plan(path, catalog=catalog, policy={"candidateCoverage": {"ocr-en": ["family-a", "family-b"]}})


def test_ready_run_plan_is_content_addressed_and_receipt_complete():
    payload = {
        "schemaVersion": 2,
        "runPlanRevision": "rev11-production-benchmark-run-plan-v3",
        "createdAtUtc": "2026-08-19T12:00:00Z",
        "ready": True,
        "reasons": [],
        "corpusId": "corpus-a",
        "corpusManifestSha256": "sha256:" + "1" * 64,
        "policyRevision": "policy-a",
        "policySha256": "sha256:" + "2" * 64,
        "catalogRevision": "catalog-a",
        "catalogSha256": "sha256:" + "3" * 64,
        "candidatePlanRevision": "plan-a",
        "candidatePlanSha256": "sha256:" + "4" * 64,
        "executor": {"revision": EXECUTOR_REVISION, "sourceSha256": "sha256:" + "e" * 64},
        "dependencyLocks": {"revision": "rev11-qualification-dependency-lock-pins-v1", "packageLockSha256": "sha256:" + "d" * 64, "uvLockSha256": "sha256:" + "c" * 64, "npmPackageCount": 2, "uvPackageCount": 2},
        "artifactPins": [{"artifactId": "model-a", "sha256": "sha256:" + "5" * 64, "expectedFilename": "model.bin"}],
        "artifactReceiptSha256s": {"model-a": "sha256:" + "6" * 64},
    }
    payload["runPlanSha256"] = run_plan_digest(payload)
    validate_run_plan(payload)
    payload["artifactPins"][0]["sha256"] = "sha256:" + "7" * 64
    with pytest.raises(RunPlanError, match="content digest mismatch"):
        validate_run_plan(payload)


def test_ready_run_plan_cannot_omit_receipt_pin():
    payload = {
        "schemaVersion": 2,
        "runPlanRevision": "rev11-production-benchmark-run-plan-v3",
        "createdAtUtc": "2026-08-19T12:00:00Z",
        "ready": True,
        "reasons": [],
        "corpusId": "corpus-a",
        "corpusManifestSha256": "sha256:" + "1" * 64,
        "policyRevision": "policy-a",
        "policySha256": "sha256:" + "2" * 64,
        "catalogRevision": "catalog-a",
        "catalogSha256": "sha256:" + "3" * 64,
        "candidatePlanRevision": "plan-a",
        "candidatePlanSha256": "sha256:" + "4" * 64,
        "executor": {"revision": EXECUTOR_REVISION, "sourceSha256": "sha256:" + "e" * 64},
        "dependencyLocks": {"revision": "rev11-qualification-dependency-lock-pins-v1", "packageLockSha256": "sha256:" + "d" * 64, "uvLockSha256": "sha256:" + "c" * 64, "npmPackageCount": 2, "uvPackageCount": 2},
        "artifactPins": [{"artifactId": "model-a", "sha256": "sha256:" + "5" * 64, "expectedFilename": "model.bin"}],
        "artifactReceiptSha256s": {},
    }
    payload["runPlanSha256"] = run_plan_digest(payload)
    with pytest.raises(RunPlanError, match="receipt pin is missing"):
        validate_run_plan(payload)


def test_active_v3_plan_has_exact_primary_source_registry_identity():
    root = Path(__file__).resolve().parents[2]
    from mte_engine.benchmark.acquisition import load_source_registry, source_for_artifact
    from mte_engine.benchmark.catalog import artifact_by_id, load_catalog
    from mte_engine.benchmark.gate import load_policy

    catalog = load_catalog(root / "engine/model-catalog/model-candidates-v1.json")
    policy = load_policy(root / "engine/benchmark/policies/benchmark-thresholds-v3.json")
    plan = load_candidate_plan(root / "engine/benchmark/candidate-plan-v3.json", catalog=catalog, policy=policy)
    registry = load_source_registry(root / "engine/model-catalog/acquisition-source-registry-v3.json")
    by_id = artifact_by_id(catalog)
    active = {artifact_id for candidate in plan["candidates"] for artifact_id in candidate["artifactIds"]}
    active.update(plan.get("supportArtifactIds", []))
    assert active == {
        "ppocrv6-small-det", "ppocrv6-medium-det", "ppocrv6-small-rec", "ppocrv6-medium-rec",
        "ppocrv5-korean-mobile-rec", "manga-ocr-base-0.1.16", "lama-big", "aot-gan-places2",
        "noto-sans-arabic-production-font",
    }
    for artifact_id in active:
        source = source_for_artifact(registry, artifact_id)
        artifact = by_id[artifact_id]
        assert source["expectedFilename"] == artifact["expectedFilename"]
        assert source["upstreamRevision"] == artifact["upstreamRevision"]
    assert "comic-text-detector-model" not in active


def test_manga_source_registry_pins_upstream_commit_and_weight_sha():
    root = Path(__file__).resolve().parents[2]
    from mte_engine.benchmark.acquisition import load_source_registry, source_for_artifact

    registry = load_source_registry(root / "engine/model-catalog/acquisition-source-registry-v3.json")
    source = source_for_artifact(registry, "manga-ocr-base-0.1.16")
    assert source["mode"] == "https-tree"
    assert "aa6573bd10b0d446cbf622e29c3e084914df9741" in source["baseUrl"]
    weight = next(item for item in source["files"] if item["path"] == "pytorch_model.bin")
    assert weight["sha256"] == "sha256:c63e0bb5b3ff798c5991de18a8e0956c7ee6d1563aca6729029815eda6f5c2eb"


def test_active_v3_font_source_is_exact_official_release_zip_member():
    root = Path(__file__).resolve().parents[2]
    from mte_engine.benchmark.acquisition import load_source_registry, source_for_artifact
    registry = load_source_registry(root / "engine/model-catalog/acquisition-source-registry-v3.json")
    source = source_for_artifact(registry, "noto-sans-arabic-production-font")
    assert source["mode"] == "https-zip-member"
    assert source["upstreamRevision"] == "NotoSansArabic-v2.013"
    assert source["retrievalUrl"].endswith("/NotoSansArabic-v2.013/NotoSansArabic-v2.013.zip")
    assert source["archiveMember"] == "NotoSansArabic/full/variable/NotoSansArabic[wdth,wght].ttf"


def test_zip_member_acquisition_record_binds_source_container_and_extracted_bytes(tmp_path: Path):
    from mte_engine.benchmark.acquisition import acquisition_record_digest, source_registry_digest, validate_acquisition_record, AcquisitionError
    artifact = tmp_path / "Font.ttf"; artifact.write_bytes(b"font-bytes")
    registry={
      "schemaVersion":3,"registryRevision":"registry-zip-v1","artifacts":{"font-a":{
        "mode":"https-zip-member","primaryDocumentation":"https://github.com/example/fonts/releases/tag/v1",
        "retrievalUrl":"https://github.com/example/fonts/releases/download/v1/font.zip","allowedHostSuffixes":["github.com","githubusercontent.com"],
        "expectedFilename":"Font.ttf","upstreamRevision":"v1","archiveMember":"Family/full/variable/Font.ttf","maxArchiveBytes":4096,"maxBytes":1024,
      }}
    }
    record={
      "schemaVersion":1,"recordId":"font-a-record","artifactId":"font-a","sourceRegistryRevision":"registry-zip-v1",
      "sourceRegistrySha256":source_registry_digest(registry),"catalogRevision":"catalog-v1","expectedFilename":"Font.ttf","upstreamRevision":"v1",
      "acquiredAtUtc":"2026-08-19T12:00:00Z","artifactSha256":sha256_path(artifact),"artifactByteSize":artifact.stat().st_size,"artifactFileCount":1,
      "files":[{"path":"Font.ttf","requestedUrl":"https://github.com/example/fonts/releases/download/v1/font.zip","resolvedUrl":"https://release-assets.githubusercontent.com/font.zip","sha256":sha256_path(artifact),"byteSize":artifact.stat().st_size}],
      "sourceContainer":{"kind":"zip","sha256":"sha256:"+"a"*64,"byteSize":2048,"memberPath":"Family/full/variable/Font.ttf"},
    }
    record["recordSha256"]=acquisition_record_digest(record)
    validate_acquisition_record(record,registry=registry,artifact_path=artifact)
    record["sourceContainer"]["memberPath"]="other.ttf"; record["recordSha256"]=acquisition_record_digest(record)
    with pytest.raises(AcquisitionError,match="sourceContainer identity mismatch"):
        validate_acquisition_record(record,registry=registry,artifact_path=artifact)


def test_acquisition_record_binds_registered_url_local_bytes_and_registry(tmp_path: Path):
    from mte_engine.benchmark.acquisition import acquisition_record_digest, source_registry_digest, validate_acquisition_record, AcquisitionError

    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"official-bytes")
    registry = {
        "schemaVersion": 2,
        "registryRevision": "registry-test-v1",
        "artifacts": {
            "model-a": {
                "mode": "direct-https-file",
                "primaryDocumentation": "https://models.example.test/docs",
                "retrievalUrl": "https://downloads.example.test/model.bin",
                "allowedHostSuffixes": ["example.test"],
                "expectedFilename": "model.bin",
                "upstreamRevision": "upstream-r1",
                "maxBytes": 1024,
            }
        },
    }
    record = {
        "schemaVersion": 1,
        "recordId": "model-a-record",
        "artifactId": "model-a",
        "sourceRegistryRevision": registry["registryRevision"],
        "sourceRegistrySha256": source_registry_digest(registry),
        "catalogRevision": "catalog-test",
        "expectedFilename": "model.bin",
        "upstreamRevision": "upstream-r1",
        "acquiredAtUtc": "2026-08-19T12:00:00Z",
        "artifactSha256": sha256_path(artifact),
        "artifactByteSize": artifact.stat().st_size,
        "artifactFileCount": 1,
        "files": [{
            "path": "model.bin",
            "requestedUrl": "https://downloads.example.test/model.bin",
            "resolvedUrl": "https://cdn.downloads.example.test/model.bin",
            "sha256": sha256_path(artifact),
            "byteSize": artifact.stat().st_size,
        }],
    }
    record["recordSha256"] = acquisition_record_digest(record)
    validate_acquisition_record(record, registry=registry, artifact_id="model-a", artifact_path=artifact)
    record["files"][0]["resolvedUrl"] = "https://attacker.invalid/model.bin"
    record["recordSha256"] = acquisition_record_digest(record)
    with pytest.raises(AcquisitionError, match="outside the registered host allowlist"):
        validate_acquisition_record(record, registry=registry, artifact_id="model-a", artifact_path=artifact)


def test_intake_refuses_automated_primary_source_without_acquisition_record(tmp_path: Path):
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    source = tmp_path / "PP-OCRv6_small_det_infer.tar"
    source.write_bytes(b"dummy")
    review = tmp_path / "review.json"
    review.write_text(json.dumps({
        "schemaVersion": 1,
        "artifactId": "ppocrv6-small-det",
        "reviewRecordId": "review-test",
        "reviewer": "unit-test",
        "reviewedAtUtc": "2026-08-19T12:00:00Z",
        "benchmarkUseStatus": "pending",
        "artifactLicenseStatus": "pending",
        "redistributionStatus": "pending",
        "retrievalUrl": "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/PP-OCRv6_small_det_infer.tar",
        "acquisitionMethod": "official-cli",
        "evidence": [{"kind": "docs", "url": "https://paddlepaddle.github.io/PaddleOCR/main/en/version3.x/module_usage/text_detection.html"}],
        "derivation": None,
    }), encoding="utf-8")
    proc = subprocess.run([
        sys.executable, str(root / "engine/scripts/intake_model_artifact.py"),
        "--catalog", str(root / "engine/model-catalog/model-candidates-v1.json"),
        "--artifact-id", "ppocrv6-small-det",
        "--source", str(source),
        "--review", str(review),
        "--source-registry", str(root / "engine/model-catalog/acquisition-source-registry-v3.json"),
        "--artifacts-dir", str(tmp_path / "artifacts"),
        "--receipts-dir", str(tmp_path / "receipts"),
    ], text=True, capture_output=True)
    assert proc.returncode != 0
    assert "require --acquisition-record" in (proc.stdout + proc.stderr)


def test_acquisition_record_requires_catalog_revision(tmp_path: Path):
    from mte_engine.benchmark.acquisition import acquisition_record_digest, source_registry_digest, validate_acquisition_record, AcquisitionError

    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"bytes")
    registry = {
        "schemaVersion": 2,
        "registryRevision": "registry-v1",
        "artifacts": {"model-a": {
            "mode": "direct-https-file",
            "primaryDocumentation": "https://example.test/docs",
            "retrievalUrl": "https://example.test/model.bin",
            "allowedHostSuffixes": ["example.test"],
            "expectedFilename": "model.bin",
            "upstreamRevision": "r1",
            "maxBytes": 1024,
        }},
    }
    record = {
        "schemaVersion": 1,
        "recordId": "r",
        "artifactId": "model-a",
        "sourceRegistryRevision": "registry-v1",
        "sourceRegistrySha256": source_registry_digest(registry),
        "expectedFilename": "model.bin",
        "upstreamRevision": "r1",
        "acquiredAtUtc": "2026-08-19T12:00:00Z",
        "artifactSha256": sha256_path(artifact),
        "artifactByteSize": artifact.stat().st_size,
        "artifactFileCount": 1,
        "files": [{"path": "model.bin", "requestedUrl": "https://example.test/model.bin", "resolvedUrl": "https://example.test/model.bin", "sha256": sha256_path(artifact), "byteSize": artifact.stat().st_size}],
    }
    record["recordSha256"] = acquisition_record_digest(record)
    with pytest.raises(AcquisitionError, match="catalogRevision"):
        validate_acquisition_record(record, registry=registry, artifact_path=artifact)


def test_acquisition_record_per_file_evidence_is_rehashed_from_local_tree(tmp_path: Path):
    from mte_engine.benchmark.acquisition import acquisition_record_digest, source_registry_digest, validate_acquisition_record, AcquisitionError

    artifact = tmp_path / "model-dir"
    artifact.mkdir()
    (artifact / "config.json").write_bytes(b"{}")
    (artifact / "weights.bin").write_bytes(b"weights")
    registry = {
        "schemaVersion": 2,
        "registryRevision": "tree-registry-v1",
        "artifacts": {"tree-model": {
            "mode": "https-tree",
            "primaryDocumentation": "https://models.example.test/docs",
            "baseUrl": "https://models.example.test/rev/",
            "allowedHostSuffixes": ["example.test"],
            "expectedFilename": "model-dir",
            "upstreamRevision": "rev-tree",
            "files": [
                {"path": "config.json", "maxBytes": 1024},
                {"path": "weights.bin", "maxBytes": 1024},
            ],
        }},
    }
    rows=[]
    for name in ("config.json", "weights.bin"):
        local=artifact/name
        rows.append({"path": name, "requestedUrl": f"https://models.example.test/rev/{name}", "resolvedUrl": f"https://models.example.test/rev/{name}", "sha256": sha256_path(local), "byteSize": local.stat().st_size})
    record={
        "schemaVersion": 1,
        "recordId": "tree-record",
        "artifactId": "tree-model",
        "sourceRegistryRevision": "tree-registry-v1",
        "sourceRegistrySha256": source_registry_digest(registry),
        "catalogRevision": "catalog-tree-v1",
        "expectedFilename": "model-dir",
        "upstreamRevision": "rev-tree",
        "acquiredAtUtc": "2026-08-19T12:00:00Z",
        "artifactSha256": sha256_path(artifact),
        "artifactByteSize": sum(row["byteSize"] for row in rows),
        "artifactFileCount": 2,
        "files": rows,
    }
    record["recordSha256"] = acquisition_record_digest(record)
    validate_acquisition_record(record, registry=registry, artifact_path=artifact)
    record["files"][0]["sha256"] = "sha256:" + "f" * 64
    record["recordSha256"] = acquisition_record_digest(record)
    with pytest.raises(AcquisitionError, match="file SHA-256 mismatch"):
        validate_acquisition_record(record, registry=registry, artifact_path=artifact)


def test_converter_review_binds_exact_converter_bytes_url_and_revision(tmp_path: Path):
    from mte_engine.benchmark.manual_artifacts import load_converter_review, ManualArtifactError
    converter = tmp_path / "exporter.py"
    converter.write_text("print('export')\n", encoding="utf-8")
    review = tmp_path / "converter-review.json"
    payload = {
        "schemaVersion": 1,
        "artifactId": "lama-big",
        "reviewRecordId": "converter-review-001",
        "reviewer": "unit-test",
        "reviewedAtUtc": "2026-08-19T12:00:00Z",
        "converterRevision": "converter-commit-abc",
        "converterSourceUrl": "https://example.invalid/exporter.py",
        "converterSourceSha256": sha256_path(converter),
        "converterUseStatus": "approved",
        "converterLicenseStatus": "approved",
        "evidence": [{"kind": "source", "url": "https://example.invalid/source"}],
    }
    review.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_converter_review(
        review, artifact_id="lama-big", converter_source=converter,
        converter_source_url=payload["converterSourceUrl"], converter_revision=payload["converterRevision"],
    )
    assert loaded["reviewRecordId"] == "converter-review-001"
    converter.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ManualArtifactError, match="converter source bytes"):
        load_converter_review(
            review, artifact_id="lama-big", converter_source=converter,
            converter_source_url=payload["converterSourceUrl"], converter_revision=payload["converterRevision"],
        )
