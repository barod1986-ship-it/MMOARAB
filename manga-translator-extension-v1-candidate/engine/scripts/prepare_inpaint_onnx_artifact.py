from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import zipfile
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.common import canonical_json, sha256_path
from mte_engine.benchmark.manual_artifacts import (
    CONTRACT_FILENAME, DERIVATION_FILENAME, MODEL_FILENAME, INPAINT_CONTRACT,
    ManualArtifactError, derivation_digest, inspect_inpaint_package,
    load_manual_policy, load_source_checkpoint_review, load_converter_review, validate_onnx_runtime,
)

DEFAULT_POLICY = ENGINE_ROOT / 'model-catalog' / 'manual-derived-artifact-policy-v1.json'


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def _zip_add_bytes(zf: zipfile.ZipFile, name: str, data: bytes) -> None:
    zf.writestr(_zip_info(name), data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def _zip_add_file(zf: zipfile.ZipFile, name: str, source: Path) -> None:
    info = _zip_info(name)
    info.file_size = source.stat().st_size
    with zf.open(info, "w", force_zip64=True) as dst, source.open("rb") as src:
        while chunk := src.read(1024 * 1024):
            dst.write(chunk)


def main() -> int:
    parser = argparse.ArgumentParser(description='Package a human-reviewed LaMa/AOT checkpoint export into the exact deterministic MTE ONNX runtime contract. This tool does not download or convert checkpoints by itself.')
    parser.add_argument('--artifact-id', required=True, choices=['lama-big','aot-gan-places2'])
    parser.add_argument('--onnx-model', required=True, type=Path)
    parser.add_argument('--source-checkpoint', required=True, type=Path)
    parser.add_argument('--source-review', required=True, type=Path)
    parser.add_argument('--converter-source', required=True, type=Path, help='Local converter/exporter source file or directory actually used to produce the ONNX bytes.')
    parser.add_argument('--converter-source-url', required=True)
    parser.add_argument('--converter-review', required=True, type=Path)
    parser.add_argument('--converter-revision', required=True)
    parser.add_argument('--operator', required=True)
    parser.add_argument('--policy', type=Path, default=DEFAULT_POLICY)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--replace', action='store_true')
    args = parser.parse_args()

    policy = load_manual_policy(args.policy)
    item = policy['artifacts'][args.artifact_id]
    if args.output.name != item['expectedFilename']:
        raise SystemExit(f"output filename must be exactly {item['expectedFilename']}")
    for path, label in ((args.onnx_model,'ONNX model'),(args.source_checkpoint,'source checkpoint'),(args.converter_source,'converter source')):
        if path.is_symlink() or not path.exists():
            raise SystemExit(f'{label} is missing or a symlink')
    review = load_source_checkpoint_review(args.source_review, artifact_id=args.artifact_id, checkpoint=args.source_checkpoint)
    converter_review = load_converter_review(
        args.converter_review, artifact_id=args.artifact_id, converter_source=args.converter_source,
        converter_source_url=args.converter_source_url, converter_revision=args.converter_revision,
    )
    runtime = validate_onnx_runtime(args.onnx_model, item)
    model_sha = sha256_path(args.onnx_model)
    source_sha = sha256_path(args.source_checkpoint)
    converter_sha = sha256_path(args.converter_source)
    source_review_sha = sha256_path(args.source_review)
    converter_review_sha = sha256_path(args.converter_review)
    created = max(review['reviewedAtUtc'], converter_review['reviewedAtUtc'])
    derivation = {
        'schemaVersion':1,
        'packagerRevision':policy['packagerRevision'],
        'artifactId':args.artifact_id,
        'candidateId':item['candidateId'],
        'runtimeContract':INPAINT_CONTRACT,
        'sourceArtifactSha256':source_sha,
        'sourceReviewRecordId':review['reviewRecordId'],
        'sourceReviewFileSha256':source_review_sha,
        'converterReviewRecordId':converter_review['reviewRecordId'],
        'converterReviewFileSha256':converter_review_sha,
        'converterRevision':args.converter_revision,
        'converterSourceUrl':args.converter_source_url,
        'converterSourceSha256':converter_sha,
        'modelSha256':model_sha,
        'createdAtUtc':created,
        'operator':args.operator,
        'runtimeValidation':runtime,
    }
    derivation['derivationSha256']=derivation_digest(derivation)
    derivation_bytes=canonical_json(derivation)
    contract={
        'schemaVersion':1,
        'contract':INPAINT_CONTRACT,
        'candidateId':item['candidateId'],
        'modelFile':MODEL_FILENAME,
        'imageInput':item['imageInput'],
        'maskInput':item['maskInput'],
        'output':item['output'],
        'tensorLayout':item['tensorLayout'],
        'imageRange':item['imageRange'],
        'maskSemantics':item['maskSemantics'],
        'padMultiple':item['padMultiple'],
        'modelSha256':model_sha,
        'derivationManifest':DERIVATION_FILENAME,
        'derivationManifestSha256':'sha256:'+hashlib.sha256(derivation_bytes).hexdigest(),
    }
    contract_bytes=canonical_json(contract)

    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.output.exists() and not args.replace:
        raise SystemExit('output already exists; use --replace only after reviewing the replacement')
    fd, tmp_name=tempfile.mkstemp(prefix='.'+args.output.name+'.', suffix='.tmp', dir=args.output.parent)
    os.close(fd)
    tmp=Path(tmp_name)
    try:
        with zipfile.ZipFile(tmp,'w', allowZip64=True) as zf:
            _zip_add_file(zf, MODEL_FILENAME, args.onnx_model)
            _zip_add_bytes(zf, CONTRACT_FILENAME, contract_bytes)
            _zip_add_bytes(zf, DERIVATION_FILENAME, derivation_bytes)
        inspected=inspect_inpaint_package(tmp,artifact_id=args.artifact_id,expected_candidate_id=item['candidateId'])
        os.replace(tmp,args.output)
        print(json.dumps({
            'artifactId':args.artifact_id,'output':str(args.output),'packageSha256':inspected['packageSha256'],
            'modelSha256':model_sha,'sourceArtifactSha256':source_sha,'converterSourceSha256':converter_sha,
            'derivationSha256':derivation['derivationSha256'],'runtimeValidation':runtime,
        },ensure_ascii=False,indent=2))
        return 0
    finally:
        tmp.unlink(missing_ok=True)

if __name__=='__main__':
    try:
        raise SystemExit(main())
    except ManualArtifactError as exc:
        raise SystemExit(str(exc))
