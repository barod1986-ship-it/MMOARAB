from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.acquisition import load_acquisition_record, load_source_registry, source_for_artifact
from mte_engine.benchmark.catalog import artifact_by_id, load_catalog, resolve_artifact_path
from mte_engine.benchmark.common import is_sha256, require_dict, require_list, sha256_path
from mte_engine.benchmark.provenance import artifact_stats, receipt_digest, validate_receipt
from mte_engine.benchmark.manual_artifacts import inspect_inpaint_package, load_manual_policy


def _load_review(path: Path, artifact_id: str) -> dict:
    try:
        review = require_dict(json.loads(path.read_text(encoding="utf-8")), label="artifact review")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"cannot read review record: {exc}") from exc
    if review.get("schemaVersion") != 1 or review.get("artifactId") != artifact_id:
        raise ValueError("review record schemaVersion/artifactId mismatch")
    for key in ("reviewRecordId", "reviewer", "reviewedAtUtc", "retrievalUrl", "acquisitionMethod"):
        if not isinstance(review.get(key), str) or not review[key].strip():
            raise ValueError(f"review record requires {key}")
    for key, allowed in (
        ("benchmarkUseStatus", {"approved", "pending", "blocked"}),
        ("artifactLicenseStatus", {"approved", "pending", "blocked"}),
        ("redistributionStatus", {"approved", "local-only", "pending", "blocked"}),
    ):
        if review.get(key) not in allowed:
            raise ValueError(f"review record has invalid {key}")
    evidence = require_list(review.get("evidence"), label="review evidence")
    if not evidence:
        raise ValueError("review evidence must not be empty")
    return review


def _copy_no_links(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise ValueError("symlink source artifacts are refused")
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination, follow_symlinks=False)
        return
    if not source.is_dir():
        raise ValueError("source artifact does not exist")
    destination.mkdir(parents=True, exist_ok=True)
    for item in sorted(source.rglob("*")):
        if item.is_symlink():
            raise ValueError("artifact trees containing symlinks are refused")
        relative = item.relative_to(source)
        target = destination / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item, target, follow_symlinks=False)
        else:
            raise ValueError("non-regular artifact entries are refused")


def main() -> int:
    parser = argparse.ArgumentParser(description="Intake an explicitly acquired local model artifact and emit a content-addressed provenance receipt. No network download is performed.")
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--source", required=True, type=Path, help="Explicit local file/directory already acquired by the operator.")
    parser.add_argument("--review", required=True, type=Path, help="Human-reviewed provenance/license/benchmark-use decision record.")
    parser.add_argument("--source-registry", type=Path, help="Primary-source acquisition registry. Required for artifacts acquired by the automated primary-source downloader.")
    parser.add_argument("--acquisition-record", type=Path, help="Content-addressed acquisition record emitted by acquire_official_artifact.py.")
    parser.add_argument("--artifacts-dir", required=True, type=Path)
    parser.add_argument("--receipts-dir", required=True, type=Path)
    parser.add_argument("--commit", action="store_true", help="Copy bytes, update catalog pin/statuses, and write receipt. Without this flag the command is dry-run only.")
    parser.add_argument("--replace", action="store_true", help="Replace an existing destination only when --commit is used.")
    args = parser.parse_args()

    catalog = load_catalog(args.catalog)
    by_id = artifact_by_id(catalog)
    artifact = by_id.get(args.artifact_id)
    if artifact is None:
        raise SystemExit(f"Unknown artifactId: {args.artifact_id}")
    review = _load_review(args.review, args.artifact_id)
    if not args.source.exists() or args.source.is_symlink():
        raise SystemExit("Source artifact is missing or is a symlink")

    derived_inspection = None
    if artifact.get("runtimeContract") == "mte-onnx-inpaint-contract-v1":
        manual_policy = load_manual_policy(ENGINE_ROOT / "model-catalog" / "manual-derived-artifact-policy-v1.json")
        policy_item = manual_policy["artifacts"].get(args.artifact_id)
        if not isinstance(policy_item, dict):
            raise SystemExit("Runtime artifact is absent from the manual-derived artifact policy")
        derived_inspection = inspect_inpaint_package(args.source, artifact_id=args.artifact_id, expected_candidate_id=str(policy_item["candidateId"]))

    source_registry = None
    acquisition_record = None
    source_entry = None
    if args.source_registry is not None:
        source_registry = load_source_registry(args.source_registry)
        source_entry = source_for_artifact(source_registry, args.artifact_id)
        if source_entry["expectedFilename"] != artifact["expectedFilename"] or source_entry["upstreamRevision"] != artifact["upstreamRevision"]:
            raise SystemExit("Source registry identity does not match catalog artifact")
        if source_entry["mode"] in {"direct-https-file", "https-tree", "https-zip-member"} and args.acquisition_record is None:
            raise SystemExit("Automated primary-source artifacts require --acquisition-record")
    if args.acquisition_record is not None:
        if source_registry is None:
            raise SystemExit("--acquisition-record requires --source-registry")
        acquisition_record = load_acquisition_record(args.acquisition_record, registry=source_registry, artifact_id=args.artifact_id, artifact_path=args.source)
        if acquisition_record.get("catalogRevision") != catalog["catalogRevision"]:
            raise SystemExit("Acquisition record catalogRevision does not match catalog")

    source_digest = sha256_path(args.source)
    source_bytes, source_files = artifact_stats(args.source)
    destination = resolve_artifact_path(args.artifacts_dir, str(artifact["expectedFilename"]), artifact_id=args.artifact_id)
    receipt_file = args.receipts_dir / f"{args.artifact_id}.receipt.json"
    summary = {
        "artifactId": args.artifact_id,
        "source": str(args.source),
        "destination": str(destination),
        "sha256": source_digest,
        "artifactByteSize": source_bytes,
        "artifactFileCount": source_files,
        "reviewRecordId": review["reviewRecordId"],
        "acquisitionRecord": str(args.acquisition_record) if args.acquisition_record else None,
        "commit": args.commit,
    }
    if not args.commit:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    if destination.exists() and not args.replace:
        raise SystemExit("Destination already exists; use --replace only after intentionally reviewing the replacement")

    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    args.receipts_dir.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=".mte-artifact-intake-", dir=args.artifacts_dir))
    staged = staging_root / str(artifact["expectedFilename"])
    try:
        _copy_no_links(args.source, staged)
        if sha256_path(staged) != source_digest:
            raise ValueError("staged artifact digest changed during copy")
        staged_bytes, staged_files = artifact_stats(staged)
        if (staged_bytes, staged_files) != (source_bytes, source_files):
            raise ValueError("staged artifact shape changed during copy")

        artifact["sha256"] = source_digest
        artifact["benchmarkUseStatus"] = review["benchmarkUseStatus"]
        artifact["artifactLicenseStatus"] = review["artifactLicenseStatus"]
        artifact["redistributionStatus"] = review["redistributionStatus"]
        acquired_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        receipt = {
            "schemaVersion": 1,
            "receiptId": f"{args.artifact_id}-{source_digest.removeprefix('sha256:')[:16]}",
            "artifactId": args.artifact_id,
            "catalogRevision": catalog["catalogRevision"],
            "expectedFilename": artifact["expectedFilename"],
            "artifactSha256": source_digest,
            "artifactByteSize": source_bytes,
            "artifactFileCount": source_files,
            "source": {
                "provenanceUrl": artifact["sourceUrl"],
                "retrievalUrl": review["retrievalUrl"],
                "upstreamRevision": artifact["upstreamRevision"],
                "acquisitionMethod": review["acquisitionMethod"],
                "acquiredAtUtc": acquired_at,
            },
            "review": {
                "reviewed": True,
                "reviewRecordId": review["reviewRecordId"],
                "reviewer": review["reviewer"],
                "reviewedAtUtc": review["reviewedAtUtc"],
                "benchmarkUseStatus": review["benchmarkUseStatus"],
                "artifactLicenseStatus": review["artifactLicenseStatus"],
                "redistributionStatus": review["redistributionStatus"],
                "evidence": review["evidence"],
            },
        }
        if acquisition_record is not None:
            acquisition_filename = f"{args.artifact_id}.acquisition.json"
            receipt["acquisition"] = {
                "recordFilename": acquisition_filename,
                "recordFileSha256": sha256_path(args.acquisition_record),
                "recordContentSha256": acquisition_record["recordSha256"],
                "sourceRegistryRevision": acquisition_record["sourceRegistryRevision"],
                "sourceRegistrySha256": acquisition_record["sourceRegistrySha256"],
            }

        if derived_inspection is not None:
            d = derived_inspection["derivation"]
            receipt["derivation"] = {
                "runtimeContract": d["runtimeContract"],
                "packagerRevision": d["packagerRevision"],
                "sourceArtifactSha256": d["sourceArtifactSha256"],
                "sourceReviewRecordId": d["sourceReviewRecordId"],
                "sourceReviewFileSha256": d["sourceReviewFileSha256"],
                "converterReviewRecordId": d["converterReviewRecordId"],
                "converterReviewFileSha256": d["converterReviewFileSha256"],
                "converterRevision": d["converterRevision"],
                "converterSourceUrl": d["converterSourceUrl"],
                "converterSourceSha256": d["converterSourceSha256"],
                "modelSha256": d["modelSha256"],
                "derivationSha256": d["derivationSha256"],
            }
        elif review.get("derivation") is not None:
            raise ValueError("non-runtime artifacts may not inject derivation provenance through the human review record")
        receipt["receiptSha256"] = receipt_digest(receipt)

        catalog_tmp = args.catalog.with_suffix(args.catalog.suffix + ".tmp")
        receipt_tmp = receipt_file.with_suffix(receipt_file.suffix + ".tmp")
        acquisition_copy_tmp = None
        acquisition_copy = None
        catalog_tmp.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        receipt_tmp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if acquisition_record is not None:
            acquisition_copy = args.receipts_dir / f"{args.artifact_id}.acquisition.json"
            acquisition_copy_tmp = acquisition_copy.with_suffix(acquisition_copy.suffix + ".tmp")
            shutil.copyfile(args.acquisition_record, acquisition_copy_tmp, follow_symlinks=False)
            # validate against a temporary receipt directory containing the copied record
            validation_dir = Path(tempfile.mkdtemp(prefix=".mte-receipt-validate-", dir=args.receipts_dir))
            try:
                shutil.copyfile(acquisition_copy_tmp, validation_dir / acquisition_copy.name, follow_symlinks=False)
                validate_receipt(receipt, catalog=catalog, artifacts_dir=staging_root, receipt_dir=validation_dir)
            finally:
                shutil.rmtree(validation_dir, ignore_errors=True)
        else:
            validate_receipt(receipt, catalog=catalog, artifacts_dir=staging_root)

        if destination.exists():
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        destination.parent.mkdir(parents=True, exist_ok=True)
        staged.replace(destination)
        if acquisition_copy_tmp is not None and acquisition_copy is not None:
            acquisition_copy_tmp.replace(acquisition_copy)
        catalog_tmp.replace(args.catalog)
        receipt_tmp.replace(receipt_file)
        print(json.dumps({**summary, "receipt": str(receipt_file), "receiptSha256": receipt["receiptSha256"]}, ensure_ascii=False, indent=2))
        return 0
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
