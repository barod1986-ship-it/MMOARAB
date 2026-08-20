from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from release_evidence import load_json, require_hex40, require_hex64, sha256_file, validate_controlled_manifest  # type: ignore
from v1_evidence_orchestrator import read_session, read_store_handoff  # type: ignore

REVISION = 'rev20-final-release-capsule-v1'
SAFE_NAME = re.compile(r'^[A-Za-z0-9._-]+$')
HEX64 = re.compile(r'^[0-9a-f]{64}$')


class CapsuleError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('utf-8')


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def safe_relative(value: str, label: str) -> str:
    p = PurePosixPath(value.replace('\\', '/'))
    if not value or p.is_absolute() or any(part in {'', '.', '..'} for part in p.parts):
        raise CapsuleError(f'{label} has an unsafe relative path: {value!r}')
    return p.as_posix()


def safe_flat_name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SAFE_NAME.fullmatch(value):
        raise CapsuleError(f'{label} has an unsafe filename')
    return value


def ensure_regular(path: Path, label: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise CapsuleError(f'{label} must be a regular non-symlink file: {path}')


def copy_verified(source: Path, target: Path, expected_sha: str | None = None) -> dict[str, Any]:
    ensure_regular(source, 'capsule source')
    before = sha256_file(source)
    if expected_sha is not None and before != require_hex64(expected_sha, f'expected hash for {source.name}'):
        raise CapsuleError(f'capsule source hash mismatch for {source.name}')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    after = sha256_file(target)
    if after != before or sha256_file(source) != before:
        raise CapsuleError(f'exact-copy integrity failure for {source.name}')
    return {'path': target.as_posix(), 'sha256': before, 'bytes': target.stat().st_size}


def parse_sums(path: Path) -> dict[str, str]:
    ensure_regular(path, 'controlled SHA256SUMS')
    result: dict[str, str] = {}
    for index, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line:
            continue
        if '  ' not in line:
            raise CapsuleError(f'controlled SHA256SUMS line {index} is malformed')
        digest, name = line.split('  ', 1)
        digest = digest.lower()
        if not HEX64.fullmatch(digest):
            raise CapsuleError(f'controlled SHA256SUMS line {index} digest is invalid')
        safe_flat_name(name, f'controlled SHA256SUMS line {index}')
        if name in result:
            raise CapsuleError(f'controlled SHA256SUMS duplicates {name}')
        result[name] = digest
    return result


def controlled_inventory(controlled_dir: Path, manifest: dict[str, Any], manifest_sha: str) -> tuple[list[dict[str, Any]], str]:
    expected: dict[str, tuple[str, str, str | None]] = {}

    extension = manifest.get('extension')
    if not isinstance(extension, dict):
        raise CapsuleError('controlled manifest extension is missing')
    ext_name = safe_flat_name(extension.get('artifact'), 'controlled extension')
    ext_sha = require_hex64(extension.get('sha256'), 'controlled extension sha256')
    expected[ext_name] = (ext_sha, 'extension', None)

    engines = manifest.get('engines')
    if not isinstance(engines, list) or not engines:
        raise CapsuleError('controlled manifest Engine list is missing')
    targets: set[str] = set()
    for item in engines:
        if not isinstance(item, dict):
            raise CapsuleError('controlled Engine entry is malformed')
        target = str(item.get('target', ''))
        if target in targets or target not in {'linux-x86_64', 'macos-arm64', 'windows-x86_64'}:
            raise CapsuleError(f'controlled Engine target is invalid or duplicated: {target}')
        targets.add(target)
        name = safe_flat_name(item.get('artifact'), f'controlled Engine {target}')
        digest = require_hex64(item.get('sha256'), f'controlled Engine {target} sha256')
        expected[name] = (digest, 'engine', target)
        meta_name = safe_flat_name(item.get('compatibilityMetadata'), f'controlled Engine metadata {target}')
        meta_sha = require_hex64(item.get('compatibilityMetadataSha256'), f'controlled Engine metadata {target} sha256')
        expected[meta_name] = (meta_sha, 'engine-compatibility-metadata', target)

    metadata = manifest.get('metadata')
    if not isinstance(metadata, list):
        raise CapsuleError('controlled manifest metadata list is malformed')
    for item in metadata:
        if not isinstance(item, dict):
            raise CapsuleError('controlled release metadata entry is malformed')
        name = safe_flat_name(item.get('artifact'), 'controlled release metadata')
        digest = require_hex64(item.get('sha256'), f'controlled metadata {name} sha256')
        if name in expected:
            raise CapsuleError(f'controlled archive duplicates output name {name}')
        expected[name] = (digest, 'release-metadata', None)

    expected['controlled-release.json'] = (manifest_sha, 'controlled-manifest', None)
    sums_path = controlled_dir / 'SHA256SUMS'
    sums = parse_sums(sums_path)
    if sums != {name: spec[0] for name, spec in expected.items()}:
        raise CapsuleError('controlled SHA256SUMS does not exactly match controlled manifest inventory')

    actual_names: set[str] = set()
    for child in controlled_dir.iterdir():
        if child.is_symlink() or not child.is_file():
            raise CapsuleError(f'controlled archive contains a non-regular entry: {child.name}')
        safe_flat_name(child.name, 'controlled archive entry')
        actual_names.add(child.name)
    required_names = set(expected) | {'SHA256SUMS'}
    if actual_names != required_names:
        extra = sorted(actual_names - required_names)
        missing = sorted(required_names - actual_names)
        raise CapsuleError(f'controlled archive inventory differs from manifest; extra={extra}, missing={missing}')

    inventory: list[dict[str, Any]] = []
    for name in sorted(expected):
        digest, kind, target = expected[name]
        source = controlled_dir / name
        ensure_regular(source, f'controlled archive {name}')
        if sha256_file(source) != digest:
            raise CapsuleError(f'controlled archive hash mismatch for {name}')
        entry: dict[str, Any] = {'kind': kind, 'sourceName': name, 'sha256': digest, 'bytes': source.stat().st_size}
        if target is not None:
            entry['target'] = target
        inventory.append(entry)
    sums_sha = sha256_file(sums_path)
    return inventory, sums_sha


def run_final_gate(root: Path, release_class: str) -> None:
    command = [
        sys.executable,
        str(root / 'scripts' / 'verify_controlled_release_ready.py'),
        '--root', str(root),
        '--target-class', release_class,
        '--gate-stage', 'final',
    ]
    result = subprocess.run(command, cwd=root, text=True, capture_output=True)
    if result.returncode != 0:
        detail = (result.stdout + result.stderr).strip()
        raise CapsuleError('final controlled release gate is not green before capsule assembly' + (f': {detail}' if detail else ''))


def _evidence_specs(root: Path, session_path: Path, release_class: str) -> list[tuple[str, str, Path]]:
    specs = [
        ('release-ready-session', 'release-ready.json', session_path),
        ('pre-final-orchestration', 'v1-orchestration-pre-final.json', root / 'release-control' / 'v1-orchestration.json'),
        ('release-state', 'release-state.json', root / 'release-control' / 'release-state.json'),
        ('smoke-records', 'smoke-records.json', root / 'release-control' / 'smoke-records.json'),
        ('profile-privacy', 'profile-privacy.json', root / 'store' / 'release' / 'profile-privacy.json'),
        ('production-freeze', 'production-profile-freeze.json', root / 'engine' / 'mte_engine' / 'benchmark' / 'production-profile-freeze.json'),
        ('npm-lock', 'package-lock.json', root / 'package-lock.json'),
        ('uv-lock', 'uv.lock', root / 'engine' / 'uv.lock'),
        ('source-integrity-manifest', 'SOURCE_SHA256SUMS.txt', root / 'SOURCE_SHA256SUMS.txt'),
    ]
    if release_class == 'public-v1':
        specs.extend([
            ('store-publication-state', 'publication-state.json', root / 'store' / 'publication-state.json'),
            ('support-channels', 'support-channels.json', root / 'release-control' / 'support-channels.json'),
            ('production-downloads', 'production-downloads.json', root / 'release-control' / 'production-downloads.json'),
            ('store-candidate-metadata', 'store-candidate.json', root / 'release' / 'store' / 'candidate.json'),
            ('store-submission-handoff', 'store-submission-handoff.json', root / 'release' / 'store' / 'store-submission-handoff.json'),
        ])
    return specs


def _assert_promoted_evidence(root: Path, session: dict[str, Any], session_path: Path) -> None:
    release_class = session['releaseClass']
    prefinal_path = root / 'release-control' / 'v1-orchestration.json'
    prefinal_expected = 'public-evidence-promoted' if release_class == 'public-v1' else 'evidence-promoted'
    prefinal = read_session(prefinal_path, prefinal_expected)
    if prefinal.get('sessionSha256') != session.get('previousSessionSha256'):
        raise CapsuleError('release-ready session is not chained to the promoted pre-final orchestration checkpoint')

    qualification = session['qualification']
    freeze = root / 'engine' / 'mte_engine' / 'benchmark' / 'production-profile-freeze.json'
    npm_lock = root / 'package-lock.json'
    uv_lock = root / 'engine' / 'uv.lock'
    for p, key, label in [
        (freeze, 'freezeSha256', 'production freeze'),
        (npm_lock, 'packageLockSha256', 'npm lock'),
        (uv_lock, 'uvLockSha256', 'uv lock'),
    ]:
        ensure_regular(p, label)
        if sha256_file(p) != require_hex64(qualification.get(key), f'orchestration qualification.{key}'):
            raise CapsuleError(f'{label} bytes differ from release-ready orchestration qualification')

    promoted = session.get('publicEvidencePromotion') if release_class == 'public-v1' else session.get('evidencePromotion')
    if not isinstance(promoted, dict):
        raise CapsuleError('release-ready orchestration lacks promoted evidence')
    checks: list[tuple[str, Path]] = [
        ('profilePrivacySha256', root / 'store' / 'release' / 'profile-privacy.json'),
        ('smokeRecordsSha256', root / 'release-control' / 'smoke-records.json'),
        ('releaseStateSha256', root / 'release-control' / 'release-state.json'),
    ]
    if release_class == 'public-v1':
        checks.extend([
            ('publicationStateSha256', root / 'store' / 'publication-state.json'),
            ('supportChannelsSha256', root / 'release-control' / 'support-channels.json'),
            ('productionDownloadsSha256', root / 'release-control' / 'production-downloads.json'),
            ('storeCandidateMetadataSha256', root / 'release' / 'store' / 'candidate.json'),
        ])
    for key, path in checks:
        ensure_regular(path, key)
        if promoted.get(key) != sha256_file(path):
            raise CapsuleError(f'{key} differs from release-ready promoted evidence')

    if release_class == 'public-v1':
        handoff_path = root / 'release' / 'store' / 'store-submission-handoff.json'
        candidate_path = root / 'release' / 'store' / 'candidate.json'
        handoff = read_store_handoff(handoff_path)
        candidate = load_json(candidate_path, 'Store candidate metadata')
        if promoted.get('storeSubmissionHandoffSha256') != handoff.get('handoffSha256'):
            raise CapsuleError('Store handoff identity differs from release-ready public evidence')
        controlled = session.get('controlled') or {}
        if handoff.get('controlledManifestSha256') != controlled.get('manifestSha256'):
            raise CapsuleError('Store handoff differs from release-ready controlled manifest')
        if candidate.get('controlledManifestSha256') != controlled.get('manifestSha256'):
            raise CapsuleError('Store candidate metadata differs from release-ready controlled manifest')
        if candidate.get('storeSubmissionHandoffSha256') != handoff.get('handoffSha256'):
            raise CapsuleError('Store candidate metadata differs from release-ready Store handoff')


def build_capsule(
    *,
    root: Path,
    session_path: Path,
    controlled_dir: Path,
    output: Path,
    finalization_source_head_sha: str,
    verify_gate: bool = True,
) -> dict[str, Any]:
    root = root.resolve()
    session_path = session_path.resolve()
    controlled_dir = controlled_dir.resolve()
    output = output.resolve()

    session = read_session(session_path, 'release-ready')
    release_id = str(session.get('releaseId', ''))
    if not SAFE_NAME.fullmatch(release_id):
        raise CapsuleError('release-ready releaseId is unsafe')
    release_class = session.get('releaseClass')
    finalization_source_head_sha = require_hex40(finalization_source_head_sha, 'finalization source head sha')
    if release_class not in {'private-v1', 'public-v1'}:
        raise CapsuleError('final release capsule supports private-v1/public-v1 only')
    if controlled_dir.name != release_id:
        raise CapsuleError('controlled archive directory does not match release-ready releaseId')
    if verify_gate:
        run_final_gate(root, release_class)

    manifest_path = controlled_dir / 'controlled-release.json'
    manifest, manifest_sha = validate_controlled_manifest(manifest_path, require_v1=True)
    if manifest.get('releaseId') != release_id or manifest.get('releaseClass') != release_class:
        raise CapsuleError('controlled manifest release identity differs from release-ready session')
    if manifest.get('sourceHeadSha') != session.get('assemblySourceHeadSha'):
        raise CapsuleError('controlled manifest assembly source differs from release-ready session')
    if manifest.get('qualifiedSourceHeadSha') != session.get('qualifiedSourceHeadSha'):
        raise CapsuleError('controlled manifest qualified source differs from release-ready session')
    controlled = session.get('controlled')
    if not isinstance(controlled, dict) or controlled.get('manifestSha256') != manifest_sha:
        raise CapsuleError('controlled manifest bytes differ from release-ready orchestration')

    inventory, controlled_sums_sha = controlled_inventory(controlled_dir, manifest, manifest_sha)
    _assert_promoted_evidence(root, session, session_path)

    if output.exists():
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise CapsuleError(f'final capsule output must not already contain files: {output}')
        output.rmdir()
    output.parent.mkdir(parents=True, exist_ok=True)
    staging: Path | None = Path(tempfile.mkdtemp(prefix=f'.{release_id}.final-', dir=output.parent))
    try:
        artifact_records: list[dict[str, Any]] = []
        for item in inventory:
            source_name = item['sourceName']
            source = controlled_dir / source_name
            relative = f'artifacts/{source_name}'
            target = staging / relative
            copied = copy_verified(source, target, item['sha256'])
            record = dict(item)
            record.pop('sourceName', None)
            record.update({'path': relative, 'bytes': copied['bytes']})
            artifact_records.append(record)
        sums_relative = 'artifacts/SHA256SUMS'
        sums_copy = copy_verified(controlled_dir / 'SHA256SUMS', staging / sums_relative, controlled_sums_sha)
        artifact_records.append({'kind': 'controlled-checksums', 'path': sums_relative, 'sha256': sums_copy['sha256'], 'bytes': sums_copy['bytes']})

        evidence_records: list[dict[str, Any]] = []
        for kind, name, source in _evidence_specs(root, session_path, release_class):
            relative = f'evidence/{name}'
            copied = copy_verified(source.resolve(), staging / relative)
            evidence_records.append({'kind': kind, 'path': relative, 'sha256': copied['sha256'], 'bytes': copied['bytes']})

        extension = manifest['extension']
        capsule: dict[str, Any] = {
            'schemaVersion': 1,
            'revision': REVISION,
            'releaseId': release_id,
            'releaseClass': release_class,
            'assemblySourceHeadSha': require_hex40(session.get('assemblySourceHeadSha'), 'release-ready assembly source'),
            'qualifiedSourceHeadSha': require_hex40(session.get('qualifiedSourceHeadSha'), 'release-ready qualified source'),
            'finalizationSourceHeadSha': finalization_source_head_sha,
            'releaseReadySessionSha256': require_hex64(session.get('sessionSha256'), 'release-ready session sha256'),
            'preFinalSessionSha256': require_hex64(session.get('previousSessionSha256'), 'release-ready previous session sha256'),
            'qualification': dict(session['qualification']),
            'controlled': {
                'manifestSha256': manifest_sha,
                'sha256SumsSha256': controlled_sums_sha,
                'protocolMajor': manifest.get('protocolMajor'),
                'exactArtifactsOnly': manifest.get('exactArtifactsOnly'),
                'rebuildDuringPromotion': manifest.get('rebuildDuringPromotion'),
            },
            'artifacts': artifact_records,
            'evidence': evidence_records,
            'delivery': {
                'extensionArtifact': extension.get('artifact'),
                'extensionSha256': require_hex64(extension.get('sha256'), 'controlled extension sha256'),
                'engineTargets': sorted(str(x.get('target')) for x in manifest.get('engines', []) if isinstance(x, dict)),
            },
        }
        if release_class == 'public-v1':
            handoff = read_store_handoff(root / 'release' / 'store' / 'store-submission-handoff.json')
            candidate = load_json(root / 'release' / 'store' / 'candidate.json', 'Store candidate metadata')
            candidate_sha = require_hex64(candidate.get('sha256'), 'Store candidate sha256')
            extension_sha = require_hex64(extension.get('sha256'), 'controlled extension sha256')
            if candidate_sha != extension_sha:
                raise CapsuleError('public Store candidate is not byte-identical to controlled Extension')
            capsule['publicStore'] = {
                'candidateArtifact': candidate.get('artifact'),
                'candidateSha256': candidate_sha,
                'byteIdenticalToControlledExtension': candidate.get('byteIdenticalToControlledExtension') is True,
                'storeSubmissionHandoffSha256': handoff.get('handoffSha256'),
            }
            if capsule['publicStore']['byteIdenticalToControlledExtension'] is not True:
                raise CapsuleError('public Store candidate is not explicitly marked byte-identical to controlled Extension')

        manifest_out = staging / 'release-manifest.json'
        atomic_json(manifest_out, capsule)

        # The checksum list covers every capsule subject except itself. It is attested separately.
        subjects: list[tuple[str, str]] = []
        for path in sorted(p for p in staging.rglob('*') if p.is_file() and p.name != 'CAPSULE_SHA256SUMS.txt'):
            if path.is_symlink():
                raise CapsuleError(f'final capsule contains a symlink: {path}')
            rel = path.relative_to(staging).as_posix()
            safe_relative(rel, 'final capsule subject')
            subjects.append((sha256_file(path), rel))
        sums_out = staging / 'CAPSULE_SHA256SUMS.txt'
        sums_out.write_text(''.join(f'{digest}  {rel}\n' for digest, rel in subjects), encoding='utf-8')

        os.replace(staging, output)
        staging = None
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

    result = verify_capsule(output)
    return result


def verify_capsule(capsule_dir: Path) -> dict[str, Any]:
    capsule_dir = capsule_dir.resolve()
    if not capsule_dir.is_dir() or capsule_dir.is_symlink():
        raise CapsuleError('final release capsule must be a regular directory')
    manifest_path = capsule_dir / 'release-manifest.json'
    manifest = load_json(manifest_path, 'final release manifest')
    if manifest.get('schemaVersion') != 1 or manifest.get('revision') != REVISION:
        raise CapsuleError('final release manifest schema/revision is unsupported')
    release_id = safe_flat_name(manifest.get('releaseId'), 'final release releaseId')
    if capsule_dir.name != release_id:
        raise CapsuleError('final capsule directory name differs from releaseId')
    if manifest.get('releaseClass') not in {'private-v1', 'public-v1'}:
        raise CapsuleError('final release manifest releaseClass is invalid')
    require_hex40(manifest.get('assemblySourceHeadSha'), 'final release assemblySourceHeadSha')
    require_hex40(manifest.get('qualifiedSourceHeadSha'), 'final release qualifiedSourceHeadSha')
    require_hex40(manifest.get('finalizationSourceHeadSha'), 'final release finalizationSourceHeadSha')
    require_hex64(manifest.get('releaseReadySessionSha256'), 'final release releaseReadySessionSha256')
    require_hex64(manifest.get('preFinalSessionSha256'), 'final release preFinalSessionSha256')

    sums_path = capsule_dir / 'CAPSULE_SHA256SUMS.txt'
    ensure_regular(sums_path, 'final capsule checksum list')
    expected: dict[str, str] = {}
    for index, line in enumerate(sums_path.read_text(encoding='utf-8').splitlines(), 1):
        if not line or '  ' not in line:
            raise CapsuleError(f'final capsule checksum line {index} is malformed')
        digest, rel = line.split('  ', 1)
        digest = digest.lower()
        if not HEX64.fullmatch(digest):
            raise CapsuleError(f'final capsule checksum line {index} digest is invalid')
        rel = safe_relative(rel, f'final capsule checksum line {index}')
        if rel == 'CAPSULE_SHA256SUMS.txt' or rel in expected:
            raise CapsuleError(f'final capsule checksum line {index} duplicates or self-references {rel}')
        expected[rel] = digest

    actual_files: set[str] = set()
    for path in capsule_dir.rglob('*'):
        if path.is_symlink():
            raise CapsuleError(f'final capsule contains a symlink: {path}')
        if path.is_dir():
            continue
        rel = path.relative_to(capsule_dir).as_posix()
        actual_files.add(rel)
    expected_files = set(expected) | {'CAPSULE_SHA256SUMS.txt'}
    if actual_files != expected_files:
        raise CapsuleError(f'final capsule file inventory mismatch; extra={sorted(actual_files-expected_files)}, missing={sorted(expected_files-actual_files)}')
    for rel, digest in expected.items():
        path = capsule_dir / rel
        ensure_regular(path, f'final capsule subject {rel}')
        if sha256_file(path) != digest:
            raise CapsuleError(f'final capsule subject hash mismatch: {rel}')

    records = []
    for key in ('artifacts', 'evidence'):
        items = manifest.get(key)
        if not isinstance(items, list) or not items:
            raise CapsuleError(f'final release manifest {key} list is missing')
        for item in items:
            if not isinstance(item, dict):
                raise CapsuleError(f'final release manifest {key} entry is malformed')
            rel = safe_relative(str(item.get('path', '')), f'final release {key} path')
            digest = require_hex64(item.get('sha256'), f'final release {key} sha256')
            if expected.get(rel) != digest:
                raise CapsuleError(f'final release {key} hash is not represented exactly in capsule checksums: {rel}')
            path = capsule_dir / rel
            if item.get('bytes') != path.stat().st_size:
                raise CapsuleError(f'final release {key} byte count differs for {rel}')
            records.append(rel)
    if len(records) != len(set(records)):
        raise CapsuleError('final release manifest duplicates artifact/evidence paths')

    ready_path = capsule_dir / 'evidence' / 'release-ready.json'
    ready = read_session(ready_path, 'release-ready')
    if ready.get('sessionSha256') != manifest.get('releaseReadySessionSha256'):
        raise CapsuleError('capsule release-ready session identity differs from release manifest')
    if ready.get('releaseId') != release_id or ready.get('releaseClass') != manifest.get('releaseClass'):
        raise CapsuleError('capsule release-ready identity differs from release manifest')
    if ready.get('previousSessionSha256') != manifest.get('preFinalSessionSha256'):
        raise CapsuleError('capsule release-ready chain differs from release manifest')

    controlled_copy = capsule_dir / 'artifacts' / 'controlled-release.json'
    controlled, controlled_sha = validate_controlled_manifest(controlled_copy, require_v1=True)
    controlled_meta = manifest.get('controlled')
    if not isinstance(controlled_meta, dict) or controlled_meta.get('manifestSha256') != controlled_sha:
        raise CapsuleError('capsule controlled manifest identity differs from release manifest')
    if ready.get('controlled', {}).get('manifestSha256') != controlled_sha:
        raise CapsuleError('capsule controlled manifest identity differs from release-ready session')
    if controlled.get('sourceHeadSha') != manifest.get('assemblySourceHeadSha') or controlled.get('qualifiedSourceHeadSha') != manifest.get('qualifiedSourceHeadSha'):
        raise CapsuleError('capsule controlled source identities differ from release manifest')

    qualification = manifest.get('qualification')
    if not isinstance(qualification, dict):
        raise CapsuleError('final release qualification payload is missing')
    copied_qual = {
        'freezeSha256': capsule_dir / 'evidence' / 'production-profile-freeze.json',
        'packageLockSha256': capsule_dir / 'evidence' / 'package-lock.json',
        'uvLockSha256': capsule_dir / 'evidence' / 'uv.lock',
    }
    for key, path in copied_qual.items():
        if sha256_file(path) != require_hex64(qualification.get(key), f'final release qualification.{key}'):
            raise CapsuleError(f'final capsule {key} differs from qualification payload')

    if manifest.get('releaseClass') == 'public-v1':
        public = manifest.get('publicStore')
        if not isinstance(public, dict) or public.get('byteIdenticalToControlledExtension') is not True:
            raise CapsuleError('public final capsule lacks exact Store candidate binding')
        extension = controlled.get('extension') or {}
        if require_hex64(public.get('candidateSha256'), 'public Store candidate sha256') != require_hex64(extension.get('sha256'), 'controlled extension sha256'):
            raise CapsuleError('public final capsule Store candidate differs from controlled Extension')
        handoff = read_store_handoff(capsule_dir / 'evidence' / 'store-submission-handoff.json')
        if public.get('storeSubmissionHandoffSha256') != handoff.get('handoffSha256'):
            raise CapsuleError('public final capsule Store handoff identity differs from copied evidence')

    return {
        'valid': True,
        'releaseId': release_id,
        'releaseClass': manifest['releaseClass'],
        'subjects': len(expected),
        'releaseManifestSha256': sha256_file(manifest_path),
        'capsuleChecksumsSha256': sha256_file(sums_path),
    }


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Build and verify the exact final V1 release capsule after the controlled final gate passes.')
    sub = p.add_subparsers(dest='command', required=True)
    q = sub.add_parser('build')
    q.add_argument('--root', type=Path, default=ROOT)
    q.add_argument('--session', type=Path, required=True)
    q.add_argument('--controlled-dir', type=Path, required=True)
    q.add_argument('--output', type=Path, required=True)
    q.add_argument('--finalization-source-head-sha', required=True)
    q.set_defaults(command_fn='build')
    q = sub.add_parser('verify')
    q.add_argument('--capsule', type=Path, required=True)
    q.set_defaults(command_fn='verify')
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command_fn == 'build':
            result = build_capsule(root=args.root, session_path=args.session, controlled_dir=args.controlled_dir, output=args.output, finalization_source_head_sha=args.finalization_source_head_sha, verify_gate=True)
        else:
            result = verify_capsule(args.capsule)
    except (CapsuleError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f'final release capsule error: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
