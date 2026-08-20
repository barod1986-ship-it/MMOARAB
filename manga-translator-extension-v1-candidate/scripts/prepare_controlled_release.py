from __future__ import annotations

import argparse
import atexit
import hashlib
import os
import json
import shutil
import sys
import tempfile
import zipfile
import re
from pathlib import Path, PurePosixPath


SAFE_NAME = re.compile(r'^[A-Za-z0-9._-]+$')
GIT_SHA = re.compile(r'^[0-9a-f]{40}$', re.I)
V1_ENGINE_TARGETS = {'windows-x86_64', 'macos-arm64', 'linux-x86_64'}
EXPECTED_REQUIRED_PERMISSIONS = {'activeTab', 'scripting', 'storage', 'sidePanel', 'alarms'}
EXPECTED_OPTIONAL_HOSTS = {'https://*/*', 'http://127.0.0.1/*'}
FORBIDDEN_SUFFIXES = {'.pem', '.key', '.p12', '.pfx', '.env', '.map'}
FORBIDDEN_PREFIXES = ('engine/', 'node_modules/', '.git/', 'tests/', 'store/')


def safe_artifact_name(path: Path, label: str) -> str:
    name = path.name
    if not SAFE_NAME.fullmatch(name):
        raise SystemExit(f'{label} filename contains unsafe characters: {name}')
    if path.is_symlink():
        raise SystemExit(f'{label} symlink inputs are refused: {path}')
    return name


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def require_digest(value: str, label: str) -> str:
    value = value.strip().lower().removeprefix('sha256:')
    if len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise SystemExit(f'{label} must be a SHA-256 hex digest')
    return value


def inspect_extension_zip(path: Path) -> dict:
    with zipfile.ZipFile(path, 'r') as archive:
        names=set()
        for info in archive.infolist():
            normalized=info.filename.replace('\\','/')
            parts=PurePosixPath(normalized).parts
            if not normalized or normalized.startswith('/') or not parts or any(part in {'.','..'} for part in parts):
                raise SystemExit(f'unsafe extension ZIP path: {info.filename}')
            if normalized in names:
                raise SystemExit(f'duplicate extension ZIP path: {info.filename}')
            names.add(normalized)
            if ((info.external_attr >> 16) & 0o170000) == 0o120000:
                raise SystemExit(f'extension ZIP symlink forbidden: {info.filename}')
            lower=normalized.lower()
            if any(lower.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
                raise SystemExit(f'forbidden controlled extension ZIP content: {info.filename}')
            if Path(lower).suffix in FORBIDDEN_SUFFIXES:
                raise SystemExit(f'forbidden controlled extension ZIP file type: {info.filename}')
        if 'manifest.json' not in names:
            raise SystemExit('extension ZIP is missing root manifest.json')
        manifest=json.loads(archive.read('manifest.json'))
    if manifest.get('manifest_version') != 3:
        raise SystemExit('controlled release requires Manifest V3')
    try:
        minimum=int(str(manifest.get('minimum_chrome_version','0')).split('.')[0])
    except ValueError:
        minimum=0
    if minimum < 148:
        raise SystemExit('controlled release requires Chrome >=148')
    if set(manifest.get('permissions', [])) != EXPECTED_REQUIRED_PERMISSIONS:
        raise SystemExit(f"controlled extension required permission drift: {manifest.get('permissions', [])}")
    if set(manifest.get('optional_host_permissions', [])) != EXPECTED_OPTIONAL_HOSTS:
        raise SystemExit(f"controlled extension optional host permission drift: {manifest.get('optional_host_permissions', [])}")
    if manifest.get('host_permissions'):
        raise SystemExit('controlled release refuses required host_permissions')
    if manifest.get('content_scripts'):
        raise SystemExit('controlled release refuses static content_scripts')
    if manifest.get('message_serialization') != 'structured_clone':
        raise SystemExit('controlled extension lost Chrome 148 structured-clone contract')
    return {'manifestVersion':manifest.get('version'), 'minimumChromeVersion':manifest.get('minimum_chrome_version')}


def checked_copy(source: Path, target: Path, expected: str) -> dict:
    if not source.is_file():
        raise SystemExit(f'artifact not found: {source}')
    safe_artifact_name(source, 'artifact')
    actual = sha256_file(source)
    if actual != expected:
        raise SystemExit(f'artifact hash mismatch for {source.name}: expected {expected}, got {actual}')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    copied = sha256_file(target)
    if copied != actual:
        raise SystemExit(f'exact-copy integrity failure for {source.name}')
    return {'artifact': target.name, 'sha256': actual, 'byteIdenticalToTestedArtifact': True, 'bytes': target.stat().st_size}


def load_compat(path: Path, artifact: Path, expected: str, release_class: str) -> tuple[dict, str]:
    if not path.is_file():
        raise SystemExit(f'Engine compatibility metadata missing: {path}')
    safe_artifact_name(path, 'Engine compatibility metadata')
    raw = path.read_bytes()
    source_digest = hashlib.sha256(raw).hexdigest()
    data = json.loads(raw)
    for key in ('target','engineVersion','protocolMajor','artifact','sha256','signed','notarized'):
        if key not in data:
            raise SystemExit(f'Engine compatibility metadata missing {key}: {path}')
    if data['artifact'] != artifact.name:
        raise SystemExit(f'Engine metadata artifact mismatch: {data["artifact"]} != {artifact.name}')
    meta_hash = require_digest(str(data['sha256']), 'Engine compatibility sha256')
    if meta_hash != expected:
        raise SystemExit(f'Engine compatibility hash mismatch for {artifact.name}')
    if int(data['protocolMajor']) != 1:
        raise SystemExit(f'unsupported Engine protocol major for {artifact.name}: {data["protocolMajor"]}')
    target = str(data['target'])
    if release_class == 'public-v1':
        if (target.startswith('windows-') or target.startswith('macos-')) and data.get('finalArtifact') is not True:
            raise SystemExit(f'public signed platform requires finalArtifact compatibility metadata for {artifact.name}')
        if target.startswith('windows-') and not bool(data['signed']):
            raise SystemExit('public Windows artifact must be signed')
        if target.startswith('macos-') and (not bool(data['signed']) or not bool(data['notarized'])):
            raise SystemExit('public macOS artifact must be signed and notarized')
    return data, source_digest



def checked_metadata_copy(source: Path, target: Path, expected_source_digest: str) -> str:
    if not source.is_file():
        raise SystemExit(f'compatibility metadata not found: {source}')
    if source.is_symlink():
        raise SystemExit(f'compatibility metadata symlink inputs are refused: {source}')
    before = sha256_file(source)
    if before != expected_source_digest:
        raise SystemExit(f'compatibility metadata changed after validation: {source.name}')
    shutil.copyfile(source, target)
    after = sha256_file(target)
    source_after = sha256_file(source)
    if before != after or before != source_after:
        raise SystemExit(f'compatibility metadata changed during exact copy: {source.name}')
    return after

def main() -> int:
    parser = argparse.ArgumentParser(description='Archive the exact tested extension ZIP and compatible Engine artifacts without rebuilding them.')
    parser.add_argument('--release-id', required=True)
    parser.add_argument('--release-class', choices=['developer-preview','private-v1','public-v1'], required=True)
    parser.add_argument('--source-head-sha', required=True, help='Assembly/evidence commit SHA used to build the exact artifacts')
    parser.add_argument('--qualified-source-head-sha', help='Runtime source commit qualified by production benchmark; required for V1')
    parser.add_argument('--extension-zip', required=True)
    parser.add_argument('--extension-sha256', required=True)
    parser.add_argument('--engine', action='append', default=[], metavar='ARTIFACT::COMPAT_JSON::SHA256')
    parser.add_argument('--metadata', action='append', default=[], metavar='FILE::SHA256')
    parser.add_argument('--out', default='release/controlled')
    args = parser.parse_args()

    release_id = args.release_id.strip()
    source_head_sha = args.source_head_sha.strip().lower()
    if not GIT_SHA.fullmatch(source_head_sha):
        raise SystemExit('--source-head-sha must be a 40-hex Git commit SHA')
    qualified_source_head_sha = (args.qualified_source_head_sha or '').strip().lower()
    if args.release_class in {'private-v1','public-v1'}:
        if not GIT_SHA.fullmatch(qualified_source_head_sha):
            raise SystemExit('--qualified-source-head-sha is required for V1 and must be a 40-hex Git commit SHA')
    elif qualified_source_head_sha and not GIT_SHA.fullmatch(qualified_source_head_sha):
        raise SystemExit('--qualified-source-head-sha must be a 40-hex Git commit SHA when provided')
    if not release_id or any(ch not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-' for ch in release_id):
        raise SystemExit('--release-id contains unsafe characters')
    out_root = Path(args.out).resolve()
    final_out = out_root / release_id
    if final_out.exists() and any(final_out.iterdir()):
        raise SystemExit(f'release directory already contains files: {final_out}')
    out_root.mkdir(parents=True, exist_ok=True)
    if final_out.exists():
        final_out.rmdir()
    staging = Path(tempfile.mkdtemp(prefix=f'.{release_id}.staging-', dir=out_root))
    atexit.register(shutil.rmtree, staging, ignore_errors=True)
    out = staging

    ext = Path(args.extension_zip).resolve()
    if not ext.is_file():
        raise SystemExit(f'extension artifact not found: {ext}')
    safe_artifact_name(ext, 'extension artifact')
    ext_digest = require_digest(args.extension_sha256, 'extension sha256')
    if sha256_file(ext) != ext_digest:
        raise SystemExit(f'artifact hash mismatch for {ext.name}: expected {ext_digest}, got {sha256_file(ext)}')
    extension_info=inspect_extension_zip(ext)
    extension = checked_copy(ext, out / ext.name, ext_digest)
    extension.update({'kind':'extension', **extension_info})

    engines=[]
    seen_targets=set()
    seen_output_names={ext.name, 'controlled-release.json', 'SHA256SUMS'}
    for item in args.engine:
        parts=item.split('::')
        if len(parts)!=3:
            raise SystemExit('--engine format is ARTIFACT::COMPAT_JSON::SHA256')
        artifact=Path(parts[0]).resolve(); compat_path=Path(parts[1]).resolve(); digest=require_digest(parts[2], 'Engine sha256')
        safe_artifact_name(artifact, 'Engine artifact'); safe_artifact_name(compat_path, 'Engine compatibility metadata')
        for output_name in (artifact.name, compat_path.name):
            if output_name in seen_output_names:
                raise SystemExit(f'controlled release output filename collision: {output_name}')
            seen_output_names.add(output_name)
        compat, compat_source_digest=load_compat(compat_path, artifact, digest, args.release_class)
        if compat['target'] in seen_targets:
            raise SystemExit(f'duplicate Engine target: {compat["target"]}')
        seen_targets.add(compat['target'])
        copied=checked_copy(artifact, out/artifact.name, digest)
        copied.update({'kind':'engine','target':compat['target'],'engineVersion':compat['engineVersion'],'protocolMajor':compat['protocolMajor'],'signed':bool(compat['signed']),'notarized':bool(compat['notarized'])})
        meta_target=out/compat_path.name
        copied['compatibilityMetadata']=meta_target.name
        copied['compatibilityMetadataSha256']=checked_metadata_copy(compat_path, meta_target, compat_source_digest)
        engines.append(copied)

    if not engines:
        raise SystemExit('controlled release requires at least one compatible Engine artifact')
    if args.release_class in {'private-v1','public-v1'} and seen_targets != V1_ENGINE_TARGETS:
        missing=sorted(V1_ENGINE_TARGETS-seen_targets)
        extra=sorted(seen_targets-V1_ENGINE_TARGETS)
        detail=[]
        if missing: detail.append('missing '+', '.join(missing))
        if extra: detail.append('unexpected '+', '.join(extra))
        raise SystemExit('V1 controlled release requires exact native target set: '+'; '.join(detail))

    metadata=[]
    for item in args.metadata:
        parts=item.split('::')
        if len(parts)!=2:
            raise SystemExit('--metadata format is FILE::SHA256')
        source=Path(parts[0]).resolve(); digest=require_digest(parts[1], 'metadata sha256')
        safe_artifact_name(source, 'release metadata')
        if source.name in seen_output_names:
            raise SystemExit(f'controlled release output filename collision: {source.name}')
        seen_output_names.add(source.name)
        copied=checked_copy(source, out/source.name, digest)
        copied.update({'kind':'release-metadata','byteIdenticalToInput':True})
        metadata.append(copied)

    required_metadata={'extension.cyclonedx.json','engine.cyclonedx-1.5.json','engine.pylock.toml','MODEL_LICENSES.json','production-profile-freeze.json'}
    if args.release_class in {'private-v1','public-v1'}:
        names={item['artifact'] for item in metadata}
        missing=sorted(required_metadata-names)
        extra=sorted(names-required_metadata)
        if missing:
            raise SystemExit('V1 controlled release metadata missing: '+', '.join(missing))
        if extra:
            raise SystemExit('V1 controlled release metadata contains unexpected files: '+', '.join(extra))

    manifest={
        'schemaVersion':2,
        'releaseId':release_id,
        'sourceHeadSha':source_head_sha,
        'qualifiedSourceHeadSha':qualified_source_head_sha or source_head_sha,
        'releaseClass':args.release_class,
        'extension':extension,
        'engines':engines,
        'metadata':metadata,
        'protocolMajor':1,
        'exactArtifactsOnly':True,
        'rebuildDuringPromotion':False,
    }
    manifest_path=out/'controlled-release.json'
    manifest_path.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    manifest_digest=sha256_file(manifest_path)
    sums=[f'{extension["sha256"]}  {extension["artifact"]}']
    for engine in engines:
        sums += [f'{engine["sha256"]}  {engine["artifact"]}', f'{engine["compatibilityMetadataSha256"]}  {engine["compatibilityMetadata"]}']
    for item in metadata:
        sums.append(f'{item["sha256"]}  {item["artifact"]}')
    sums.append(f'{manifest_digest}  {manifest_path.name}')
    (out/'SHA256SUMS').write_text('\n'.join(sums)+'\n', encoding='utf-8')
    os.replace(out, final_out)
    manifest_path = final_out / 'controlled-release.json'
    print(json.dumps({'manifest':str(manifest_path),'sha256':manifest_digest,'artifacts':1+len(engines)+len(metadata)}, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
