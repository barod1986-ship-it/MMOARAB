from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tomllib
import zipfile
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'scripts') not in sys.path:
    sys.path.insert(0, str(ROOT / 'scripts'))
from release_evidence import validate_smoke_observation

HEX64 = re.compile(r'^[0-9a-f]{64}$', re.I)
SAFE_NAME = re.compile(r'^[A-Za-z0-9._-]+$')
REQUIRED_SMOKE_CHECKS = ('install', 'activate', 'translateFixture', 'restore')
V1_ENGINE_TARGETS = {'windows-x86_64', 'macos-arm64', 'linux-x86_64'}
EXPECTED_REQUIRED_PERMISSIONS = {'activeTab', 'scripting', 'storage', 'sidePanel', 'alarms'}
EXPECTED_OPTIONAL_HOSTS = {'https://*/*', 'http://127.0.0.1/*'}
FORBIDDEN_SUFFIXES = {'.pem', '.key', '.p12', '.pfx', '.env', '.map'}
FORBIDDEN_PREFIXES = ('engine/', 'node_modules/', '.git/', 'tests/', 'store/')


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path, label: str, blockers: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        blockers.append(f'{label} is missing')
        return None
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        blockers.append(f'{label} is invalid JSON: {exc}')
        return None
    if not isinstance(value, dict):
        blockers.append(f'{label} must contain a JSON object')
        return None
    return value


def safe_child(base: Path, name: str, label: str, blockers: list[str], *, flat: bool = True) -> Path | None:
    if not isinstance(name, str) or not name or name.startswith(('/', '\\')):
        blockers.append(f'{label} path is invalid')
        return None
    pp = PurePosixPath(name.replace('\\', '/'))
    if any(part in {'', '.', '..'} for part in pp.parts):
        blockers.append(f'{label} path is unsafe: {name}')
        return None
    if flat and (len(pp.parts) != 1 or not SAFE_NAME.fullmatch(pp.name)):
        blockers.append(f'{label} must be a flat safe filename: {name}')
        return None
    resolved = (base / Path(*pp.parts)).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError:
        blockers.append(f'{label} escapes its release directory')
        return None
    return resolved


def valid_digest(value: Any) -> bool:
    return isinstance(value, str) and bool(HEX64.fullmatch(value.removeprefix('sha256:')))


def normalized_digest(value: str) -> str:
    return value.removeprefix('sha256:').lower()


def verify_package_lock(root: Path, blockers: list[str]) -> None:
    package_path = root / 'package.json'
    lock_path = root / 'package-lock.json'
    package = load_json(package_path, 'package.json', blockers)
    lock = load_json(lock_path, 'package-lock.json', blockers)
    if package is None or lock is None:
        return
    if lock.get('lockfileVersion') != 3:
        blockers.append('package-lock.json must be npm lockfileVersion 3')
    if lock.get('name') != package.get('name') or lock.get('version') != package.get('version'):
        blockers.append('package-lock.json root name/version do not match package.json')
    packages = lock.get('packages')
    if not isinstance(packages, dict) or not isinstance(packages.get(''), dict):
        blockers.append('package-lock.json has no root packages entry')
        return
    root_entry = packages['']
    for key in ('dependencies', 'devDependencies'):
        expected = package.get(key, {})
        actual = root_entry.get(key, {})
        if actual != expected:
            blockers.append(f'package-lock.json root {key} do not exactly match package.json')
        if not isinstance(expected, dict):
            continue
        for name, requested in expected.items():
            entry = packages.get(f'node_modules/{name}')
            if not isinstance(entry, dict):
                blockers.append(f'package-lock.json is missing direct dependency entry for {name}')
                continue
            if isinstance(requested, str) and re.fullmatch(r'\d+\.\d+\.\d+(?:[-+].+)?', requested):
                if entry.get('version') != requested:
                    blockers.append(f'package-lock.json resolved {name}={entry.get("version")} instead of exact {requested}')
            if entry.get('link') is not True and not isinstance(entry.get('integrity'), str):
                blockers.append(f'package-lock.json dependency {name} has no integrity digest')


def dependency_name(spec: str) -> str | None:
    value = spec.strip()
    if not value:
        return None
    if value.startswith(('-', '.')):
        return None
    match = re.match(r'^([A-Za-z0-9_.-]+)', value)
    return match.group(1).lower().replace('_', '-') if match else None


def exact_pin(spec: str) -> tuple[str, str] | None:
    match = re.match(r'^([A-Za-z0-9_.-]+)==([^;\s]+)', spec.strip())
    if not match:
        return None
    return match.group(1).lower().replace('_', '-'), match.group(2)


def verify_uv_lock(root: Path, blockers: list[str]) -> None:
    pyproject_path = root / 'engine' / 'pyproject.toml'
    lock_path = root / 'engine' / 'uv.lock'
    if not lock_path.is_file():
        blockers.append('engine/uv.lock is missing')
        return
    try:
        pyproject = tomllib.loads(pyproject_path.read_text(encoding='utf-8'))
        lock = tomllib.loads(lock_path.read_text(encoding='utf-8'))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        blockers.append(f'engine/uv.lock or pyproject.toml is invalid TOML: {exc}')
        return
    if lock.get('version') != 1:
        blockers.append('engine/uv.lock has an unsupported lock format version')
    packages = lock.get('package')
    if not isinstance(packages, list) or not packages:
        blockers.append('engine/uv.lock contains no package graph')
        return
    by_name: dict[str, list[dict[str, Any]]] = {}
    for item in packages:
        if isinstance(item, dict) and isinstance(item.get('name'), str):
            by_name.setdefault(item['name'].lower().replace('_', '-'), []).append(item)
    project = pyproject.get('project', {})
    project_name = str(project.get('name', '')).lower().replace('_', '-')
    project_version = project.get('version')
    roots = by_name.get(project_name, [])
    if not any(item.get('version') == project_version and isinstance(item.get('source'), dict) for item in roots):
        blockers.append('engine/uv.lock does not contain the current project version')
    specs: list[str] = list(project.get('dependencies', []) or [])
    for values in (project.get('optional-dependencies', {}) or {}).values():
        if isinstance(values, list):
            specs.extend(x for x in values if isinstance(x, str))
    for spec in specs:
        name = dependency_name(spec)
        if name and name not in by_name:
            blockers.append(f'engine/uv.lock is missing direct dependency {name}')
        pin = exact_pin(spec)
        if pin and not any(item.get('version') == pin[1] for item in by_name.get(pin[0], [])):
            blockers.append(f'engine/uv.lock does not resolve exact pin {pin[0]}=={pin[1]}')


def inspect_extension_zip(path: Path, blockers: list[str]) -> dict[str, Any] | None:
    try:
        with zipfile.ZipFile(path, 'r') as archive:
            seen: set[str] = set()
            for info in archive.infolist():
                normalized = info.filename.replace('\\', '/')
                pp = PurePosixPath(normalized)
                if not normalized or normalized.startswith('/') or any(part in {'', '.', '..'} for part in pp.parts):
                    blockers.append(f'extension ZIP contains unsafe path: {info.filename}')
                    return None
                if normalized in seen:
                    blockers.append(f'extension ZIP contains duplicate path: {info.filename}')
                    return None
                seen.add(normalized)
                if ((info.external_attr >> 16) & 0o170000) == 0o120000:
                    blockers.append(f'extension ZIP contains forbidden symlink: {info.filename}')
                    return None
                lower = normalized.lower()
                if any(lower.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
                    blockers.append(f'extension ZIP contains forbidden release content: {info.filename}')
                    return None
                if Path(lower).suffix in FORBIDDEN_SUFFIXES:
                    blockers.append(f'extension ZIP contains forbidden file type: {info.filename}')
                    return None
            if 'manifest.json' not in seen:
                blockers.append('extension ZIP is missing root manifest.json')
                return None
            manifest = json.loads(archive.read('manifest.json'))
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        blockers.append(f'extension ZIP is invalid: {exc}')
        return None
    if manifest.get('manifest_version') != 3:
        blockers.append('controlled extension is not Manifest V3')
    try:
        minimum = int(str(manifest.get('minimum_chrome_version', '0')).split('.')[0])
    except ValueError:
        minimum = 0
    if minimum < 148:
        blockers.append('controlled extension minimum_chrome_version is below 148')
    if set(manifest.get('permissions', [])) != EXPECTED_REQUIRED_PERMISSIONS:
        blockers.append('controlled extension required permission drift')
    if set(manifest.get('optional_host_permissions', [])) != EXPECTED_OPTIONAL_HOSTS:
        blockers.append('controlled extension optional host permission drift')
    if manifest.get('host_permissions'):
        blockers.append('controlled extension has required host_permissions')
    if manifest.get('content_scripts'):
        blockers.append('controlled extension has static content_scripts')
    if manifest.get('message_serialization') != 'structured_clone':
        blockers.append('controlled extension lost Chrome 148 structured-clone contract')
    return manifest


def parse_sums(path: Path, blockers: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.is_file():
        blockers.append('controlled archive SHA256SUMS is missing')
        return result
    for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line:
            continue
        if '  ' not in line:
            blockers.append(f'SHA256SUMS line {lineno} is malformed')
            continue
        digest, name = line.split('  ', 1)
        if not valid_digest(digest) or not SAFE_NAME.fullmatch(name):
            blockers.append(f'SHA256SUMS line {lineno} is invalid')
            continue
        if name in result:
            blockers.append(f'SHA256SUMS duplicates {name}')
            continue
        result[name] = normalized_digest(digest)
    return result


def verify_controlled_manifest(root: Path, state: dict[str, Any], blockers: list[str]) -> tuple[dict[str, Any] | None, Path | None, str | None]:
    artifacts = state.get('artifacts') if isinstance(state.get('artifacts'), dict) else {}
    manifest_rel = artifacts.get('controlledManifest')
    if not isinstance(manifest_rel, str) or not manifest_rel:
        blockers.append('controlled release manifest is not recorded')
        return None, None, None
    controlled_root = (root / 'release' / 'controlled').resolve()
    manifest_path = safe_child(controlled_root, manifest_rel.removeprefix('release/controlled/'), 'controlled manifest', blockers, flat=False)
    if manifest_path is None or not manifest_path.is_file():
        blockers.append('controlled release manifest file is missing')
        return None, manifest_path, None
    manifest = load_json(manifest_path, 'controlled release manifest', blockers)
    if manifest is None:
        return None, manifest_path, None
    release_dir = manifest_path.parent
    manifest_sha = sha256_file(manifest_path)
    if manifest.get('schemaVersion') != 2:
        blockers.append('controlled release manifest schema is not v2')
    source_head = manifest.get('sourceHeadSha')
    if not isinstance(source_head, str) or not re.fullmatch(r'[0-9a-f]{40}', source_head, re.I):
        blockers.append('controlled release manifest sourceHeadSha is invalid')
    qualified_source_head = manifest.get('qualifiedSourceHeadSha')
    if not isinstance(qualified_source_head, str) or not re.fullmatch(r'[0-9a-f]{40}', qualified_source_head, re.I):
        blockers.append('controlled release manifest qualifiedSourceHeadSha is invalid')
    if manifest.get('releaseClass') == 'developer-preview' and qualified_source_head != source_head:
        blockers.append('developer-preview controlled manifest qualifiedSourceHeadSha must equal sourceHeadSha')
    if manifest.get('releaseClass') != state.get('releaseClass'):
        blockers.append('controlled manifest releaseClass differs from release state')
    if manifest.get('exactArtifactsOnly') is not True or manifest.get('rebuildDuringPromotion') is not False:
        blockers.append('controlled manifest does not enforce exact-artifact promotion')
    if manifest.get('protocolMajor') != 1:
        blockers.append('controlled manifest protocolMajor is not 1')
    if not isinstance(manifest.get('releaseId'), str) or not SAFE_NAME.fullmatch(manifest['releaseId']):
        blockers.append('controlled manifest releaseId is invalid')
    elif release_dir.name != manifest['releaseId']:
        blockers.append('controlled manifest releaseId does not match its directory')

    expected_files = {'controlled-release.json'}
    sums_expected: dict[str, str] = {'controlled-release.json': manifest_sha}

    extension = manifest.get('extension')
    if not isinstance(extension, dict):
        blockers.append('controlled manifest extension entry is missing')
    else:
        name = extension.get('artifact')
        digest = extension.get('sha256')
        path = safe_child(release_dir, name, 'extension artifact', blockers) if isinstance(name, str) else None
        if not valid_digest(digest):
            blockers.append('controlled manifest extension SHA-256 is invalid')
        elif path is not None:
            expected_files.add(path.name)
            sums_expected[path.name] = normalized_digest(digest)
            if not path.is_file():
                blockers.append('controlled extension artifact file is missing')
            else:
                actual = sha256_file(path)
                if actual != normalized_digest(digest):
                    blockers.append('controlled extension artifact hash does not match manifest')
                if extension.get('bytes') != path.stat().st_size:
                    blockers.append('controlled extension artifact byte count does not match manifest')
                if extension.get('byteIdenticalToTestedArtifact') is not True:
                    blockers.append('controlled extension is not marked byte-identical to tested artifact')
                zip_manifest = inspect_extension_zip(path, blockers)
                if zip_manifest is not None:
                    if extension.get('manifestVersion') != zip_manifest.get('version'):
                        blockers.append('controlled extension manifest version metadata is stale')
                    if str(extension.get('minimumChromeVersion')) != str(zip_manifest.get('minimum_chrome_version')):
                        blockers.append('controlled extension minimum Chrome metadata is stale')
        state_sha = artifacts.get('extensionSha256')
        if valid_digest(digest) and state_sha != normalized_digest(digest):
            blockers.append('release state extension hash differs from controlled manifest')

    engines = manifest.get('engines')
    targets: set[str] = set()
    if not isinstance(engines, list) or not engines:
        blockers.append('controlled release has no Engine artifacts')
        engines = []
    for index, engine in enumerate(engines):
        if not isinstance(engine, dict):
            blockers.append(f'controlled Engine entry {index} is invalid')
            continue
        target = engine.get('target')
        if not isinstance(target, str) or target not in V1_ENGINE_TARGETS:
            blockers.append(f'controlled Engine entry {index} has unsupported target')
            continue
        if target in targets:
            blockers.append(f'controlled release duplicates Engine target {target}')
        targets.add(target)
        name = engine.get('artifact')
        digest = engine.get('sha256')
        path = safe_child(release_dir, name, f'Engine artifact {target}', blockers) if isinstance(name, str) else None
        if not valid_digest(digest):
            blockers.append(f'Engine artifact SHA-256 is invalid for {target}')
        elif path is not None:
            expected_files.add(path.name)
            sums_expected[path.name] = normalized_digest(digest)
            if not path.is_file():
                blockers.append(f'Engine artifact is missing for {target}')
            else:
                if sha256_file(path) != normalized_digest(digest):
                    blockers.append(f'Engine artifact hash mismatch for {target}')
                if engine.get('bytes') != path.stat().st_size:
                    blockers.append(f'Engine artifact byte count mismatch for {target}')
                if engine.get('byteIdenticalToTestedArtifact') is not True:
                    blockers.append(f'Engine artifact is not marked exact-tested bytes for {target}')
        meta_name = engine.get('compatibilityMetadata')
        meta_digest = engine.get('compatibilityMetadataSha256')
        meta_path = safe_child(release_dir, meta_name, f'Engine compatibility metadata {target}', blockers) if isinstance(meta_name, str) else None
        if not valid_digest(meta_digest):
            blockers.append(f'Engine compatibility metadata SHA-256 is invalid for {target}')
        elif meta_path is not None:
            expected_files.add(meta_path.name)
            sums_expected[meta_path.name] = normalized_digest(meta_digest)
            meta = load_json(meta_path, f'Engine compatibility metadata {target}', blockers)
            if meta_path.is_file() and sha256_file(meta_path) != normalized_digest(meta_digest):
                blockers.append(f'Engine compatibility metadata hash mismatch for {target}')
            if meta is not None:
                expected_hash = f'sha256:{normalized_digest(digest)}' if valid_digest(digest) else None
                comparisons = {
                    'target': target,
                    'engineVersion': engine.get('engineVersion'),
                    'protocolMajor': engine.get('protocolMajor'),
                    'artifact': name,
                    'sha256': expected_hash,
                    'signed': bool(engine.get('signed')),
                    'notarized': bool(engine.get('notarized')),
                }
                for key, value in comparisons.items():
                    if meta.get(key) != value:
                        blockers.append(f'Engine compatibility metadata {key} mismatch for {target}')
                if state.get('releaseClass') == 'public-v1' and (target.startswith('windows-') or target.startswith('macos-')) and meta.get('finalArtifact') is not True:
                    blockers.append(f'public signed Engine compatibility metadata is not finalized for {target}')
        if engine.get('protocolMajor') != 1:
            blockers.append(f'Engine protocol major is unsupported for {target}')
        if state.get('releaseClass') == 'public-v1':
            if target.startswith('windows-') and engine.get('signed') is not True:
                blockers.append('public Windows Engine artifact is not signed')
            if target.startswith('macos-') and (engine.get('signed') is not True or engine.get('notarized') is not True):
                blockers.append('public macOS Engine artifact is not signed and notarized')

    metadata_entries = manifest.get('metadata')
    if metadata_entries is None:
        metadata_entries = []
    if not isinstance(metadata_entries, list):
        blockers.append('controlled release metadata list is invalid')
        metadata_entries = []
    metadata_names: set[str] = set()
    for index, item in enumerate(metadata_entries):
        if not isinstance(item, dict):
            blockers.append(f'controlled release metadata entry {index} is invalid')
            continue
        name = item.get('artifact')
        digest = item.get('sha256')
        path = safe_child(release_dir, name, f'release metadata {index}', blockers) if isinstance(name, str) else None
        if not valid_digest(digest):
            blockers.append(f'release metadata SHA-256 is invalid for entry {index}')
            continue
        if path is None:
            continue
        if path.name in metadata_names:
            blockers.append(f'controlled release duplicates metadata file {path.name}')
        metadata_names.add(path.name)
        expected_files.add(path.name)
        sums_expected[path.name] = normalized_digest(digest)
        if not path.is_file():
            blockers.append(f'controlled release metadata file is missing: {path.name}')
            continue
        if sha256_file(path) != normalized_digest(digest):
            blockers.append(f'controlled release metadata hash mismatch: {path.name}')
        if item.get('bytes') != path.stat().st_size:
            blockers.append(f'controlled release metadata byte count mismatch: {path.name}')
        if item.get('byteIdenticalToInput') is not True:
            blockers.append(f'controlled release metadata is not marked byte-identical to input: {path.name}')
    if state.get('releaseClass') in {'private-v1', 'public-v1'}:
        required_metadata = {'extension.cyclonedx.json', 'engine.cyclonedx-1.5.json', 'engine.pylock.toml', 'MODEL_LICENSES.json', 'production-profile-freeze.json'}
        if metadata_names != required_metadata:
            missing = sorted(required_metadata - metadata_names)
            extra = sorted(metadata_names - required_metadata)
            if missing:
                blockers.append(f'V1 controlled release metadata is missing: {", ".join(missing)}')
            if extra:
                blockers.append(f'V1 controlled release metadata has unexpected files: {", ".join(extra)}')

    sums = parse_sums(release_dir / 'SHA256SUMS', blockers)
    expected_files.add('SHA256SUMS')
    if sums and sums != sums_expected:
        missing = sorted(set(sums_expected) - set(sums))
        extra = sorted(set(sums) - set(sums_expected))
        wrong = sorted(name for name in set(sums_expected) & set(sums) if sums[name] != sums_expected[name])
        if missing:
            blockers.append(f'SHA256SUMS is missing entries: {", ".join(missing)}')
        if extra:
            blockers.append(f'SHA256SUMS contains untracked entries: {", ".join(extra)}')
        if wrong:
            blockers.append(f'SHA256SUMS contains wrong hashes: {", ".join(wrong)}')
    entries = list(release_dir.iterdir())
    non_regular = sorted(p.name for p in entries if p.is_symlink() or not p.is_file())
    if non_regular:
        blockers.append(f'controlled release directory contains non-regular/untracked entries: {", ".join(non_regular)}')
    actual_files = {p.name for p in entries}
    if actual_files != expected_files:
        extras = sorted(actual_files - expected_files)
        missing = sorted(expected_files - actual_files)
        if extras:
            blockers.append(f'controlled release directory has untracked files: {", ".join(extras)}')
        if missing:
            blockers.append(f'controlled release directory is missing files: {", ".join(missing)}')
    state_targets = artifacts.get('engineTargets')
    if not isinstance(state_targets, list) or any(not isinstance(x, str) for x in state_targets):
        blockers.append('release state Engine target list is missing or invalid')
    elif len(state_targets) != len(set(state_targets)) or set(state_targets) != targets:
        blockers.append('release state Engine target list differs from controlled manifest')
    return manifest, manifest_path, manifest_sha


def parse_browser_major(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    match = re.match(r'^(\d+)(?:\.|$)', value.strip())
    return int(match.group(1)) if match else None


def smoke_record_valid(record: dict[str, Any], manifest: dict[str, Any], manifest_sha: str) -> bool:
    try:
        validate_smoke_observation(record, manifest=manifest, manifest_sha256=manifest_sha)
    except ValueError:
        return False
    return True

def verify_smoke(root: Path, state: dict[str, Any], manifest: dict[str, Any] | None, manifest_sha: str | None, production_fingerprints: dict[str, str] | None, blockers: list[str], *, require_store_installed: bool = True) -> None:
    data = load_json(root / 'release-control' / 'smoke-records.json', 'smoke records', blockers)
    if data is None:
        return
    if data.get('schemaVersion') != 2:
        blockers.append('smoke records schema is not v2')
    if manifest_sha is not None and data.get('controlledManifestSha256') != manifest_sha:
        blockers.append('smoke records are not bound to the controlled manifest bytes')
    if manifest is not None and data.get('sourceHeadSha') != manifest.get('sourceHeadSha'):
        blockers.append('smoke records sourceHeadSha differs from controlled manifest')
    records = data.get('records')
    if not isinstance(records, list):
        blockers.append('smoke records list is invalid')
        return
    ids: set[str] = set()
    usable: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            blockers.append('smoke record is not an object')
            continue
        rid = record.get('id')
        if not isinstance(rid, str) or not rid or rid in ids:
            blockers.append('smoke record IDs must be unique non-empty strings')
            continue
        ids.add(rid)
        if manifest is not None and manifest_sha is not None and smoke_record_valid(record, manifest, manifest_sha):
            usable.append(record)

    audit = state.get('audit') if isinstance(state.get('audit'), dict) else {}
    baseline = audit.get('chromeBaselineMajor')
    stable = audit.get('currentStableMajorAtAudit')
    if baseline != 148:
        blockers.append('release audit Chrome baseline must remain exactly 148')
    if not isinstance(stable, int) or isinstance(stable, bool) or stable < 148:
        blockers.append('release audit current Stable Chrome major is missing or invalid')
    def unpacked(major: int) -> bool:
        return any(r.get('kind') == 'unpacked-extension' and r.get('platform') == 'browser' and parse_browser_major(r.get('browserVersion')) == major for r in usable)
    baseline_pass = isinstance(baseline, int) and unpacked(baseline)
    stable_pass = isinstance(stable, int) and unpacked(stable)
    smoke_state = state.get('smoke') if isinstance(state.get('smoke'), dict) else {}
    blockers_state = state.get('v1Blockers') if isinstance(state.get('v1Blockers'), dict) else {}
    if not baseline_pass:
        blockers.append(f'fresh unpacked Chrome {baseline} smoke evidence is missing or invalid')
    if not stable_pass:
        blockers.append(f'fresh unpacked current Stable Chrome {stable} smoke evidence is missing or invalid')
    if smoke_state.get('freshUnpackedChrome148Passed') is not baseline_pass:
        blockers.append('release-state Chrome 148 smoke flag does not match evidence')
    if smoke_state.get('freshUnpackedCurrentStablePassed') is not stable_pass:
        blockers.append('release-state current Stable smoke flag does not match evidence')
    if blockers_state.get('chrome148RealBrowserGate') is not baseline_pass:
        blockers.append('release-state Chrome 148 lifecycle flag does not match evidence')
    if blockers_state.get('currentStableRealBrowserGate') is not stable_pass:
        blockers.append('release-state current Stable lifecycle flag does not match evidence')

    target_records = {
        r.get('platform') for r in usable
        if r.get('kind') == 'engine-artifact' and isinstance(r.get('platform'), str)
    }
    targets = {e.get('target') for e in (manifest.get('engines', []) if isinstance(manifest, dict) else []) if isinstance(e, dict) and isinstance(e.get('target'), str)}
    for target in sorted(targets - target_records):
        blockers.append(f'fresh Engine artifact smoke evidence is missing for {target}')
    declared_targets = set(smoke_state.get('freshEngineArtifactPassedTargets') or [])
    if declared_targets != (targets & target_records):
        blockers.append('release-state Engine smoke targets do not exactly match evidence')

    if state.get('releaseClass') in {'private-v1', 'public-v1'}:
        production_smoke = [r for r in usable if r.get('kind') == 'engine-artifact' and r.get('platform') in targets]
        if not production_smoke or any(r.get('profileId') != 'default-v1' or r.get('profileStateAtTest') != 'ready' for r in production_smoke):
            blockers.append('V1 Engine smoke does not prove default-v1 was ready and translated successfully')
        if production_fingerprints is None or any(
            r.get('profileFingerprint') != f"sha256:{production_fingerprints.get(str(r.get('platform')), '')}"
            for r in production_smoke
        ):
            blockers.append('V1 Engine smoke profile fingerprint does not match the per-target frozen privacy/profile descriptor')
    if state.get('releaseClass') == 'public-v1' and require_store_installed:
        store_records = [r for r in usable if r.get('kind') == 'store-installed-extension' and r.get('platform') == 'browser']
        store_majors = {parse_browser_major(r.get('browserVersion')) for r in store_records}
        required_store_majors = {baseline, stable} if isinstance(baseline, int) and isinstance(stable, int) else set()
        store_pass = bool(required_store_majors) and required_store_majors.issubset(store_majors)
        if not store_pass:
            blockers.append(f'Store-installed extension smoke evidence is missing for Chrome majors {sorted(required_store_majors)}')
        if smoke_state.get('storeInstalledVersionPassed') is not store_pass:
            blockers.append('release-state Store-installed smoke flag does not match evidence')


def verify_production_freeze(root: Path, state: dict[str, Any], blockers: list[str]) -> dict[str, Any] | None:
    if state.get('releaseClass') == 'developer-preview':
        return None
    sys.path.insert(0, str(root / 'engine'))
    try:
        from mte_engine.benchmark.freeze import load_freeze  # type: ignore
        from mte_engine.benchmark.dependency_locks import dependency_lock_pins  # type: ignore
        from mte_engine.benchmark.common import canonical_json, sha256_bytes  # type: ignore
        from mte_engine.benchmark.candidate_plan import candidate_plan_digest, load_candidate_plan  # type: ignore
        from mte_engine.benchmark.gate import load_policy  # type: ignore
        from mte_engine.benchmark.source_binding import verify_current_source_binding  # type: ignore
        freeze = load_freeze(root / 'engine' / 'mte_engine' / 'benchmark' / 'production-profile-freeze.json')
        if freeze is not None and freeze.get('dependencyLocks') != dependency_lock_pins(root):
            blockers.append('production ML freeze dependency-lock pins do not match current package-lock.json/engine/uv.lock bytes')
            freeze = None
        if freeze is not None:
            active_policy = load_policy(root / 'engine' / 'benchmark' / 'policies' / 'benchmark-thresholds-v3.json')
            if freeze.get('policyRevision') != active_policy.get('policyRevision') or freeze.get('policySha256') != sha256_bytes(canonical_json(active_policy)):
                blockers.append('production ML freeze is not bound to the active benchmark policy bytes')
                freeze = None
        if freeze is not None:
            active_plan = load_candidate_plan(root / 'engine' / 'benchmark' / 'candidate-plan-v3.json')
            if freeze.get('candidatePlanSha256') != candidate_plan_digest(active_plan):
                blockers.append('production ML freeze is not bound to the active candidate-plan bytes')
                freeze = None
        if freeze is not None:
            try:
                verify_current_source_binding(root, freeze.get('qualifiedSource'))
            except ValueError as exc:
                blockers.append(f'production ML freeze qualified runtime source binding does not match current source: {exc}')
                freeze = None
    except Exception as exc:  # release gate must fail closed on import/runtime problems
        blockers.append(f'production ML freeze validation failed: {exc}')
        return None
    ready = freeze is not None
    declared = (state.get('v1Blockers') or {}).get('phase5bProductionFreezeReady')
    if not ready:
        blockers.append('production ML Gate D freeze is missing or invalid')
    if declared is not ready:
        blockers.append('release-state production ML freeze flag does not match validated freeze evidence')
    return freeze if ready else None


def verify_native_support(root: Path, state: dict[str, Any], manifest: dict[str, Any] | None, blockers: list[str]) -> None:
    if state.get('releaseClass') == 'developer-preview':
        return
    if manifest is None:
        blockers.append('V1 native Engine artifact support evidence cannot be validated without a controlled manifest')
        return
    engines = manifest.get('engines') if isinstance(manifest.get('engines'), list) else []
    targets = {e.get('target') for e in engines if isinstance(e, dict)}
    ready = targets == V1_ENGINE_TARGETS
    if not ready:
        blockers.append(f'V1 requires all native Engine targets: {", ".join(sorted(V1_ENGINE_TARGETS))}')
    declared = (state.get('v1Blockers') or {}).get('phase7NativeSupportReady')
    if declared is not ready:
        blockers.append('release-state native support flag does not match controlled artifact evidence')
    claims = load_json(root / 'engine' / 'packaging' / 'support-claims.json', 'native support claims', blockers)
    if state.get('releaseClass') == 'public-v1' and claims is not None:
        entries = claims.get('targets') if isinstance(claims.get('targets'), list) else []
        claimed = {x.get('id') for x in entries if isinstance(x, dict) and x.get('publicSupportClaimed') is True}
        if claimed != V1_ENGINE_TARGETS:
            blockers.append('public V1 native support claims are not audited/enabled for every supported target')


def verify_release_metadata(root: Path, state: dict[str, Any], manifest: dict[str, Any] | None, manifest_path: Path | None, freeze: dict[str, Any] | None, blockers: list[str]) -> None:
    if state.get('releaseClass') == 'developer-preview':
        return
    if manifest is None or manifest_path is None:
        blockers.append('V1 release metadata cannot be validated without a controlled manifest')
        return
    release_dir = manifest_path.parent
    required = ['extension.cyclonedx.json', 'engine.cyclonedx-1.5.json', 'engine.pylock.toml', 'MODEL_LICENSES.json', 'production-profile-freeze.json']
    for name in required:
        path = release_dir / name
        if not path.is_file() or path.stat().st_size == 0:
            blockers.append(f'V1 release metadata is missing from controlled archive: {name}')
    for name in ('extension.cyclonedx.json', 'engine.cyclonedx-1.5.json'):
        path = release_dir / name
        if path.is_file():
            value = load_json(path, name, blockers)
            if value is not None and (value.get('bomFormat') != 'CycloneDX' or not isinstance(value.get('components'), list)):
                blockers.append(f'{name} failed CycloneDX schema sanity checks')
    pylock = release_dir / 'engine.pylock.toml'
    if pylock.is_file():
        try:
            value = tomllib.loads(pylock.read_text(encoding='utf-8'))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            blockers.append(f'engine.pylock.toml is invalid TOML: {exc}')
        else:
            if not isinstance(value, dict) or not value:
                blockers.append('engine.pylock.toml is empty or structurally invalid')
    controlled_freeze = release_dir / 'production-profile-freeze.json'
    source_freeze = root / 'engine' / 'mte_engine' / 'benchmark' / 'production-profile-freeze.json'
    if controlled_freeze.is_file() and source_freeze.is_file() and sha256_file(controlled_freeze) != sha256_file(source_freeze):
        blockers.append('controlled archive production freeze bytes differ from the source-qualified freeze')
    if freeze is not None and manifest.get('qualifiedSourceHeadSha') != (freeze.get('qualifiedSource') or {}).get('sourceHeadSha'):
        blockers.append('controlled manifest qualifiedSourceHeadSha differs from production qualification sourceHeadSha')
    model_path = release_dir / 'MODEL_LICENSES.json'
    if model_path.is_file():
        model = load_json(model_path, 'MODEL_LICENSES.json', blockers)
        if model is not None:
            inventory = model.get('artifacts')
            if not isinstance(inventory, list) or not inventory:
                blockers.append('MODEL_LICENSES.json has no release artifact inventory')
            elif freeze is not None:
                by_id = {item.get('artifactId'): item for item in inventory if isinstance(item, dict) and isinstance(item.get('artifactId'), str)}
                pins = freeze.get('selectedArtifacts') if isinstance(freeze.get('selectedArtifacts'), list) else []
                for pin in pins:
                    if not isinstance(pin, dict) or not isinstance(pin.get('artifactId'), str):
                        continue
                    artifact_id = pin['artifactId']
                    item = by_id.get(artifact_id)
                    if not isinstance(item, dict):
                        blockers.append(f'MODEL_LICENSES.json is missing frozen artifact {artifact_id}')
                        continue
                    if not valid_digest(item.get('sha256')) or normalized_digest(str(item.get('sha256'))) != normalized_digest(str(pin.get('sha256'))):
                        blockers.append(f'MODEL_LICENSES.json hash differs from freeze for {artifact_id}')
                    if not isinstance(item.get('licenseSpdx'), str) or not item['licenseSpdx'].strip():
                        blockers.append(f'MODEL_LICENSES.json has no SPDX license for {artifact_id}')
                    if item.get('redistribution') not in {'approved', 'download-only'}:
                        blockers.append(f'MODEL_LICENSES.json has non-installable redistribution state for {artifact_id}')



def verify_v1_ml_runtime_evidence(root: Path, state: dict[str, Any], freeze: dict[str, Any] | None, blockers: list[str]) -> None:
    if state.get('releaseClass') == 'developer-preview':
        return
    flags = state.get('v1Blockers') if isinstance(state.get('v1Blockers'), dict) else {}
    if flags.get('productionRuntimeAdaptersComplete') is not True:
        blockers.append('V1 production runtime adapter implementation is not marked complete')

    role_ready = False
    inpainter_ready = False
    if freeze is not None:
        try:
            sys.path.insert(0, str(root / 'engine'))
            from mte_engine.benchmark.gate import load_policy  # type: ignore
            policy = load_policy(root / 'engine' / 'benchmark' / 'policies' / 'benchmark-thresholds-v3.json')
            role_policy = policy.get('roleSafety') if isinstance(policy.get('roleSafety'), dict) else {}
            role = freeze.get('roleSafetyQualification') if isinstance(freeze.get('roleSafetyQualification'), dict) else {}
            zero_fields = (
                'sentToTranslatorRate',
                'eraseInpaintMaskOverlapRate',
                'changedPixelRateAfterEncodeDecode',
                'uncertainDestructiveEditRate',
                'protectedConflictSilentOverwriteCount',
            )
            recall = role.get('roleClassifierSfxProtectedRecall')
            role_ready = (
                isinstance(role_policy.get('productionRevision'), str)
                and role.get('roleClassifierRevision') == role_policy.get('productionRevision')
                and isinstance(recall, (int, float)) and not isinstance(recall, bool)
                and float(recall) >= float(role_policy.get('sfxProtectedRecallMin', 1.0))
                and all(role.get(name) in (0, 0.0) for name in zero_fields)
                and isinstance(role.get('independentGroundTruthPages'), int)
                and not isinstance(role.get('independentGroundTruthPages'), bool)
                and role.get('independentGroundTruthPages', 0) >= 10
            )

            selected = freeze.get('selected') if isinstance(freeze.get('selected'), dict) else {}
            qualification = freeze.get('inpaintingQualification') if isinstance(freeze.get('inpaintingQualification'), dict) else {}
            candidate_id = selected.get('inpainter')
            artifact_id = {'lama-inpaint': 'lama-big', 'aot-inpaint': 'aot-gan-places2'}.get(candidate_id)
            pins = freeze.get('selectedArtifacts') if isinstance(freeze.get('selectedArtifacts'), list) else []
            pin = next((item for item in pins if isinstance(item, dict) and item.get('artifactId') == artifact_id), None)
            threshold = float((policy.get('qualityThresholds') or {}).get('inpaintingHumanScoreMin', float('inf')))
            score = qualification.get('humanScore')
            inpainter_ready = (
                artifact_id is not None
                and qualification.get('candidateId') == candidate_id
                and isinstance(score, (int, float)) and not isinstance(score, bool) and float(score) >= threshold
                and qualification.get('humanCriticalFailures') == 0
                and qualification.get('criticalReviewFailures') == 0
                and isinstance(qualification.get('pagesReviewed'), int)
                and not isinstance(qualification.get('pagesReviewed'), bool)
                and qualification.get('pagesReviewed', 0) >= int((policy.get('humanReviewThresholds') or {}).get('inpaintingPagesMin', 1))
                and isinstance(pin, dict)
                and pin.get('kind') == 'inpaint'
                and valid_digest(pin.get('sha256'))
            )
        except (OSError, ValueError, TypeError) as exc:
            blockers.append(f'V1 ML runtime evidence could not be derived from the production freeze: {exc}')

    if not role_ready:
        blockers.append('production role/SFX classifier qualification evidence is missing or invalid')
    if flags.get('productionRoleSfxClassifierReady') is not role_ready:
        blockers.append('release-state role/SFX readiness flag does not match frozen qualification evidence')
    if not inpainter_ready:
        blockers.append('production inpainting winner qualification evidence is missing or invalid')
    if flags.get('productionInpainterRuntimeReady') is not inpainter_ready:
        blockers.append('release-state inpainting readiness flag does not match frozen qualification evidence')


def verify_remote_transfer_consent_implementation(root: Path, state: dict[str, Any], blockers: list[str]) -> bool:
    declared = (state.get('v1Blockers') or {}).get('remoteTextTransferConsentReady')
    required = state.get('releaseClass') in {'private-v1', 'public-v1'} or declared is True
    if not required:
        return False
    verifier_path = root / 'scripts' / 'verify_remote_transfer_consent_contract.py'
    if not verifier_path.is_file():
        blockers.append('remote-transfer consent source verifier is missing')
        return False
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location('mte_remote_transfer_consent_contract', verifier_path)
        if spec is None or spec.loader is None:
            raise RuntimeError('could not load verifier module')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        local: list[str] = []
        ready = bool(module.verify_remote_transfer_consent_contract(root, local))
    except Exception as exc:
        blockers.append(f'remote-transfer consent implementation verification failed: {exc}')
        ready = False
        local = []
    for item in local:
        blockers.append(f'remote-transfer consent implementation: {item}')
    if declared is not ready:
        blockers.append('release-state remote-transfer consent readiness flag does not match verified source implementation')
    if state.get('releaseClass') in {'private-v1', 'public-v1'} and not ready:
        blockers.append('V1 release requires a verified remote-transfer consent implementation')
    return ready

def verify_profile_privacy(root: Path, state: dict[str, Any], manifest: dict[str, Any] | None, manifest_sha: str | None, remote_consent_ready: bool, blockers: list[str]) -> dict[str, str] | None:
    if state.get('releaseClass') == 'developer-preview':
        return None
    privacy = load_json(root / 'store' / 'release' / 'profile-privacy.json', 'production profile privacy descriptor', blockers)
    if privacy is None:
        return None
    if privacy.get('schemaVersion') != 2:
        blockers.append('production profile privacy descriptor schema is not v2')
    if privacy.get('profileId') != 'default-v1':
        blockers.append('production privacy descriptor is not for default-v1')
    fingerprints = privacy.get('profileFingerprintsByTarget')
    normalized: dict[str, str] | None = None
    if not isinstance(fingerprints, dict) or set(fingerprints) != V1_ENGINE_TARGETS:
        blockers.append('production profile privacy descriptor does not contain the exact per-target V1 fingerprint set')
    else:
        values: dict[str, str] = {}
        for target, fingerprint in fingerprints.items():
            if not valid_digest(fingerprint):
                blockers.append(f'frozen production profile fingerprint is missing or invalid for {target}')
            else:
                values[target] = normalized_digest(str(fingerprint))
        if len(values) == len(V1_ENGINE_TARGETS):
            normalized = values
    descriptor = privacy.get('privacyDescriptor')
    if not isinstance(descriptor, dict):
        blockers.append('frozen production privacy descriptor is missing')
    else:
        required = ('imageLeavesDevice', 'ocrTextLeavesDevice', 'visualContextLeavesDevice')
        if set(descriptor) != set(required) or any(type(descriptor.get(key)) is not bool for key in required):
            blockers.append('production privacy descriptor must use exactly three explicit boolean transfer fields')
        remote = any(descriptor.get(key) is True for key in required)
        if remote:
            if privacy.get('remoteTransferConsentImplemented') is not True:
                blockers.append('remote-transfer production profile release descriptor does not assert the versioned consent gate')
            if privacy.get('remoteTransferDisclosureVersion') != '2026-08-19.remote-transfer.v1':
                blockers.append('remote-transfer production profile disclosure version is missing or stale')
            if not remote_consent_ready:
                blockers.append('remote-transfer production profile consent gate is not verified in executable source')
            providers = privacy.get('externalProviderNames')
            if not isinstance(providers, list) or not providers or any(not isinstance(x, str) or not x.strip() for x in providers):
                blockers.append('remote-transfer production profile does not name external provider(s)')
        elif privacy.get('externalProviderNames') not in ([], None):
            blockers.append('local-only production profile unexpectedly names external providers')
    if manifest_sha is None or privacy.get('materializedFromControlledManifestSha256') != manifest_sha:
        blockers.append('production profile/privacy descriptor is not materialized from the exact controlled manifest')
    if manifest is None or privacy.get('sourceHeadSha') != manifest.get('sourceHeadSha'):
        blockers.append('production profile/privacy descriptor sourceHeadSha differs from controlled manifest')
    return normalized

def verify_v1_orchestration(root: Path, state: dict[str, Any], manifest: dict[str, Any] | None, manifest_sha: str | None, freeze: dict[str, Any] | None, blockers: list[str], *, gate_stage: str = 'final') -> None:
    if state.get('releaseClass') == 'developer-preview':
        return
    path = root / 'release-control' / 'v1-orchestration.json'
    if not path.is_file():
        blockers.append('V1 evidence orchestration checkpoint is missing')
        return
    expected_stage = 'evidence-promoted'
    if state.get('releaseClass') == 'public-v1' and gate_stage == 'final':
        expected_stage = 'public-evidence-promoted'
    try:
        sys.path.insert(0, str(root / 'scripts'))
        from v1_evidence_orchestrator import read_session  # type: ignore
        session = read_session(path, expected_stage)
    except Exception as exc:
        blockers.append(f'V1 evidence orchestration checkpoint is invalid: {exc}')
        return
    if manifest is None or manifest_sha is None:
        blockers.append('V1 orchestration cannot bind without a controlled manifest')
        return
    if session.get('releaseId') != manifest.get('releaseId') or session.get('releaseClass') != state.get('releaseClass'):
        blockers.append('V1 orchestration release identity differs from controlled release state')
    if session.get('assemblySourceHeadSha') != manifest.get('sourceHeadSha'):
        blockers.append('V1 orchestration assembly commit differs from controlled manifest')
    if session.get('qualifiedSourceHeadSha') != manifest.get('qualifiedSourceHeadSha'):
        blockers.append('V1 orchestration qualified commit differs from controlled manifest')
    controlled = session.get('controlled') if isinstance(session.get('controlled'), dict) else {}
    if controlled.get('manifestSha256') != manifest_sha:
        blockers.append('V1 orchestration controlled-manifest digest differs from archived manifest')
    qualification = session.get('qualification') if isinstance(session.get('qualification'), dict) else {}
    freeze_path = root / 'engine' / 'mte_engine' / 'benchmark' / 'production-profile-freeze.json'
    if freeze_path.is_file() and qualification.get('freezeSha256') != sha256_file(freeze_path):
        blockers.append('V1 orchestration production freeze bytes differ from promoted freeze')
    if freeze is not None and qualification.get('freezeIdentitySha256') != normalized_digest(str(freeze.get('freezeSha256', ''))):
        blockers.append('V1 orchestration freeze identity differs from production freeze')
    evidence = session.get('evidencePromotion') if isinstance(session.get('evidencePromotion'), dict) else {}
    expected_files = {
        'profilePrivacySha256': root / 'store' / 'release' / 'profile-privacy.json',
        'smokeRecordsSha256': root / 'release-control' / 'smoke-records.json',
        'releaseStateSha256': root / 'release-control' / 'release-state.json',
    }
    # Public finalization intentionally supersedes the pre-Store smoke/release-state hashes
    # with a second, post-Store promotion checkpoint. The pre-Store hashes remain enforced
    # by the store-candidate gate before any Store submission handoff is created.
    if not (state.get('releaseClass') == 'public-v1' and gate_stage == 'final'):
        for key, evidence_path in expected_files.items():
            if not evidence_path.is_file() or evidence.get(key) != sha256_file(evidence_path):
                blockers.append(f'V1 orchestration {key} differs from promoted release evidence')
    if state.get('releaseClass') == 'public-v1' and gate_stage == 'final':
        public_evidence = session.get('publicEvidencePromotion') if isinstance(session.get('publicEvidencePromotion'), dict) else {}
        public_files = {
            'profilePrivacySha256': root / 'store' / 'release' / 'profile-privacy.json',
            'smokeRecordsSha256': root / 'release-control' / 'smoke-records.json',
            'releaseStateSha256': root / 'release-control' / 'release-state.json',
            'publicationStateSha256': root / 'store' / 'publication-state.json',
            'supportChannelsSha256': root / 'release-control' / 'support-channels.json',
            'productionDownloadsSha256': root / 'release-control' / 'production-downloads.json',
            'storeCandidateMetadataSha256': root / 'release' / 'store' / 'candidate.json',
        }
        for key, evidence_path in public_files.items():
            if not evidence_path.is_file() or public_evidence.get(key) != sha256_file(evidence_path):
                blockers.append(f'V1 public orchestration {key} differs from promoted public evidence')
        handoff_path = root / 'release' / 'store' / 'store-submission-handoff.json'
        candidate_path = root / 'release' / 'store' / 'candidate.json'
        try:
            from v1_evidence_orchestrator import read_store_handoff  # type: ignore
            handoff = read_store_handoff(handoff_path)
        except Exception as exc:
            blockers.append(f'V1 public Store submission handoff is missing or invalid: {exc}')
            handoff = None
        candidate = load_json(candidate_path, 'Store candidate metadata', blockers) if candidate_path.is_file() else None
        if handoff is not None:
            if public_evidence.get('storeSubmissionHandoffSha256') != handoff.get('handoffSha256'):
                blockers.append('V1 public orchestration Store handoff identity differs from downloaded Store handoff')
            if handoff.get('controlledManifestSha256') != manifest_sha:
                blockers.append('V1 public Store handoff controlled-manifest identity differs from final archive')
            if handoff.get('orchestrationSessionSha256') != session.get('previousSessionSha256'):
                blockers.append('V1 public Store handoff is not bound to the pre-Store evidence-promoted checkpoint')
        if candidate is None:
            blockers.append('V1 public Store candidate metadata is missing for finalization')
        elif handoff is not None:
            if candidate.get('controlledManifestSha256') != manifest_sha or candidate.get('storeSubmissionHandoffSha256') != handoff.get('handoffSha256'):
                blockers.append('V1 public Store candidate is not bound to the final controlled manifest/handoff')
            extension = manifest.get('extension') if isinstance(manifest.get('extension'), dict) else {}
            if normalized_digest(str(candidate.get('sha256', ''))) != normalized_digest(str(extension.get('sha256', ''))):
                blockers.append('V1 public Store candidate hash differs from controlled Extension')


def verify_public(root: Path, state: dict[str, Any], blockers: list[str]) -> None:
    if state.get('releaseClass') != 'public-v1':
        return
    store = load_json(root / 'store' / 'publication-state.json', 'store publication state', blockers)
    channels = load_json(root / 'release-control' / 'support-channels.json', 'support channels', blockers)
    public = state.get('public') if isinstance(state.get('public'), dict) else {}
    if store is not None:
        if state.get('publicReleaseChosen') is not True or store.get('publicDistributionChosen') is not True:
            blockers.append('public release has not been explicitly chosen in both release states')
    required_flags = {
        'storeApprovedOrStaged': 'Chrome Web Store item is not approved/staged',
        'productionEngineDownloadLinksVerified': 'production Engine download links are not hash-verified',
        'supportChannelReady': 'support channel is not ready',
        'rollbackRunbookReviewed': 'rollback runbook has not been reviewed',
        'previousStoreArtifactArchived': 'previous Store artifact is not archived',
        'previousEngineArtifactsArchived': 'previous Engine artifacts are not archived',
    }
    for key, message in required_flags.items():
        if public.get(key) is not True:
            blockers.append(message)
    if channels is not None and channels.get('ready') is not True:
        blockers.append('support-channels.json is not ready')
    pct = public.get('initialDeployPercentage')
    if pct is not None:
        if not isinstance(pct, (int, float)) or isinstance(pct, bool) or not 0 < pct <= 100:
            blockers.append('initial deploy percentage must be >0 and <=100')
        elif pct < 100 and public.get('partialRolloutEligible') is not True:
            blockers.append('partial rollout configured without confirmed eligibility')


def verify_source_manifest(root: Path, blockers: list[str]) -> None:
    sys.path.insert(0, str(root / 'scripts'))
    try:
        from source_integrity import verify_source_integrity  # type: ignore
        errors = verify_source_integrity(root)
    except Exception as exc:
        blockers.append(f'source integrity verifier failed: {exc}')
        return
    blockers.extend(f'source integrity: {error}' for error in errors)


def main() -> int:
    parser = argparse.ArgumentParser(description='Fail-closed evidence verifier for a controlled V1 release.')
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument(
        '--target-class',
        choices=('developer-preview', 'private-v1', 'public-v1'),
        help='Audit readiness as the requested release class without mutating release-state.json.',
    )
    parser.add_argument(
        '--gate-stage',
        choices=('final', 'store-candidate'),
        default='final',
        help='Use store-candidate only for public-v1 pre-Store immutable evidence; final requires post-Store public evidence.',
    )
    args = parser.parse_args()
    root = args.root.resolve()
    blockers: list[str] = []
    state = load_json(root / 'release-control' / 'release-state.json', 'release state', blockers)
    if state is None:
        for blocker in blockers:
            print(f'- {blocker}', file=sys.stderr)
        return 2
    if state.get('schemaVersion') != 1:
        blockers.append('release state schema is not v1')
    if state.get('releaseClass') not in {'developer-preview', 'private-v1', 'public-v1'}:
        blockers.append('releaseClass is invalid')
    if args.target_class is not None:
        state = dict(state)
        state['releaseClass'] = args.target_class
    if args.gate_stage == 'store-candidate' and state.get('releaseClass') != 'public-v1':
        blockers.append('store-candidate gate is valid only for public-v1')

    verify_source_manifest(root, blockers)
    verify_package_lock(root, blockers)
    verify_uv_lock(root, blockers)
    lock_flags = state.get('v1Blockers') if isinstance(state.get('v1Blockers'), dict) else {}
    package_exists = (root / 'package-lock.json').is_file()
    uv_exists = (root / 'engine' / 'uv.lock').is_file()
    if lock_flags.get('packageLockCommitted') is not package_exists:
        blockers.append('release-state package lock flag does not match source tree')
    if lock_flags.get('uvLockCommitted') is not uv_exists:
        blockers.append('release-state uv lock flag does not match source tree')

    manifest, _manifest_path, manifest_sha = verify_controlled_manifest(root, state, blockers)
    remote_consent_ready = verify_remote_transfer_consent_implementation(root, state, blockers)
    production_fingerprints = verify_profile_privacy(root, state, manifest, manifest_sha, remote_consent_ready, blockers)
    verify_smoke(root, state, manifest, manifest_sha, production_fingerprints, blockers, require_store_installed=args.gate_stage == 'final')
    freeze = verify_production_freeze(root, state, blockers)
    verify_v1_ml_runtime_evidence(root, state, freeze, blockers)
    verify_native_support(root, state, manifest, blockers)
    verify_release_metadata(root, state, manifest, _manifest_path, freeze, blockers)
    verify_v1_orchestration(root, state, manifest, manifest_sha, freeze, blockers, gate_stage=args.gate_stage)
    if args.gate_stage == 'final':
        verify_public(root, state, blockers)

    if blockers:
        print(f'Controlled release blocked ({len(blockers)}):', file=sys.stderr)
        for blocker in blockers:
            print(f'- {blocker}', file=sys.stderr)
        return 2
    manifest_name = Path(str((state.get('artifacts') or {}).get('controlledManifest'))).name
    print(f'Controlled release ready: {state.get("releaseClass")}; {manifest_name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
