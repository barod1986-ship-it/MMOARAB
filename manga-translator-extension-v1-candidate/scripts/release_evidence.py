from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

HEX64 = re.compile(r'^[0-9a-f]{64}$', re.I)
HEX40 = re.compile(r'^[0-9a-f]{40}$', re.I)
V1_ENGINE_TARGETS = ('linux-x86_64', 'macos-arm64', 'windows-x86_64')
REQUIRED_SMOKE_CHECKS = ('install', 'activate', 'translateFixture', 'restore')


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('utf-8')


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def require_hex64(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f'{label} must be a SHA-256 string')
    normalized = value.removeprefix('sha256:').lower()
    if not HEX64.fullmatch(normalized):
        raise ValueError(f'{label} must be 64 hex characters')
    return normalized


def require_hex40(value: Any, label: str) -> str:
    if not isinstance(value, str) or not HEX40.fullmatch(value):
        raise ValueError(f'{label} must be a 40-hex Git commit SHA')
    return value.lower()


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'{label} is invalid JSON: {exc}') from exc
    if not isinstance(value, dict):
        raise ValueError(f'{label} must contain a JSON object')
    return value


def parse_utc(value: Any, label: str = 'testedAtUtc') -> datetime:
    if not isinstance(value, str):
        raise ValueError(f'{label} must be an ISO-8601 UTC timestamp')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError(f'{label} must be an ISO-8601 UTC timestamp') from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f'{label} must use UTC')
    return parsed.astimezone(timezone.utc)


def controlled_artifact_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    extension = manifest.get('extension')
    if isinstance(extension, dict) and isinstance(extension.get('artifact'), str):
        result['browser'] = extension
    engines = manifest.get('engines')
    if isinstance(engines, list):
        for item in engines:
            if isinstance(item, dict) and isinstance(item.get('target'), str):
                result[item['target']] = item
    return result


def validate_controlled_manifest(path: Path, *, require_v1: bool = True) -> tuple[dict[str, Any], str]:
    manifest = load_json(path, 'controlled release manifest')
    if manifest.get('schemaVersion') != 2:
        raise ValueError('controlled release manifest must use schemaVersion 2')
    release_class = manifest.get('releaseClass')
    if release_class not in {'developer-preview', 'private-v1', 'public-v1'}:
        raise ValueError('controlled release manifest has invalid releaseClass')
    require_hex40(manifest.get('sourceHeadSha'), 'controlled manifest sourceHeadSha')
    qualified = require_hex40(manifest.get('qualifiedSourceHeadSha'), 'controlled manifest qualifiedSourceHeadSha')
    if release_class == 'developer-preview' and qualified != manifest.get('sourceHeadSha'):
        raise ValueError('developer-preview controlled manifest qualifiedSourceHeadSha must equal sourceHeadSha')
    if manifest.get('exactArtifactsOnly') is not True or manifest.get('rebuildDuringPromotion') is not False:
        raise ValueError('controlled release manifest does not enforce exact artifact promotion')
    if require_v1 and release_class not in {'private-v1', 'public-v1'}:
        raise ValueError('V1 smoke evidence requires a private-v1/public-v1 controlled manifest')
    digest = sha256_file(path)
    for key, item in controlled_artifact_map(manifest).items():
        require_hex64(item.get('sha256'), f'controlled artifact {key} sha256')
        if not isinstance(item.get('artifact'), str) or not item['artifact']:
            raise ValueError(f'controlled artifact {key} name is missing')
    return manifest, digest


def validate_checks(checks: Any) -> dict[str, bool]:
    if not isinstance(checks, dict):
        raise ValueError('smoke checks must be an object')
    if set(checks) != set(REQUIRED_SMOKE_CHECKS):
        raise ValueError('smoke checks must contain exactly install/activate/translateFixture/restore')
    if any(checks.get(name) is not True for name in REQUIRED_SMOKE_CHECKS):
        raise ValueError('all smoke checks must be true')
    return {name: True for name in REQUIRED_SMOKE_CHECKS}


def validate_privacy_descriptor(value: Any) -> dict[str, bool]:
    if not isinstance(value, dict):
        raise ValueError('privacyDescriptor must be an object')
    keys = ('imageLeavesDevice', 'ocrTextLeavesDevice', 'visualContextLeavesDevice')
    if set(value) != set(keys) or any(type(value.get(key)) is not bool for key in keys):
        raise ValueError('privacyDescriptor must contain exactly three explicit boolean transfer fields')
    return {key: bool(value[key]) for key in keys}


def validate_providers(value: Any, privacy: dict[str, bool]) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError('externalProviderNames must contain non-empty strings')
    if len(value) != len(set(value)):
        raise ValueError('externalProviderNames must be unique')
    remote = any(privacy.values())
    if remote and not value:
        raise ValueError('remote-transfer profile must name at least one external provider')
    if not remote and value:
        raise ValueError('local-only profile must not name external providers')
    return list(value)


def validate_smoke_observation(
    observation: dict[str, Any],
    *,
    manifest: dict[str, Any],
    manifest_sha256: str,
    require_engine_profile: bool = True,
) -> dict[str, Any]:
    if observation.get('schemaVersion') != 2:
        raise ValueError('smoke observation must use schemaVersion 2')
    if observation.get('artifactManifestSha256') != manifest_sha256:
        raise ValueError('smoke observation is not bound to the controlled manifest bytes')
    if observation.get('sourceHeadSha') != manifest.get('sourceHeadSha'):
        raise ValueError('smoke observation sourceHeadSha differs from controlled manifest')
    if observation.get('cleanEnvironment') is not True:
        raise ValueError('smoke observation must come from a clean environment')
    parse_utc(observation.get('testedAtUtc'))
    validate_checks(observation.get('checks'))
    record_id = observation.get('id')
    if not isinstance(record_id, str) or not record_id or len(record_id) > 160:
        raise ValueError('smoke observation id is invalid')

    kind = observation.get('kind')
    artifacts = controlled_artifact_map(manifest)
    if kind == 'engine-artifact':
        target = observation.get('platform')
        if target not in V1_ENGINE_TARGETS:
            raise ValueError('engine smoke platform is not a V1 target')
        expected = artifacts.get(str(target))
        if not isinstance(expected, dict):
            raise ValueError(f'controlled manifest has no Engine artifact for {target}')
        if observation.get('artifact') != expected.get('artifact'):
            raise ValueError(f'engine smoke artifact name differs from controlled manifest for {target}')
        if require_hex64(observation.get('artifactSha256'), 'engine smoke artifactSha256') != require_hex64(expected.get('sha256'), 'controlled Engine sha256'):
            raise ValueError(f'engine smoke artifact hash differs from controlled manifest for {target}')
        if require_engine_profile:
            if observation.get('profileId') != 'default-v1' or observation.get('profileStateAtTest') != 'ready':
                raise ValueError('V1 Engine smoke must prove default-v1 ready')
            require_hex64(observation.get('profileFingerprint'), 'engine smoke profileFingerprint')
            privacy = validate_privacy_descriptor(observation.get('privacyDescriptor'))
            validate_providers(observation.get('externalProviderNames'), privacy)
            if observation.get('cleanInstallVerified') is not True or observation.get('installationCleanupVerified') is not True:
                raise ValueError('Engine smoke must prove clean artifact installation/extraction and cleanup')
            installation_mode = observation.get('installationMode')
            expected_pkg = str(expected.get('artifact', '')).lower().endswith('.pkg')
            if expected_pkg and installation_mode != 'macos-pkg-system-install':
                raise ValueError('macOS .pkg Engine smoke must prove a real system package installation')
            if not expected_pkg and installation_mode != 'portable-clean-extract':
                raise ValueError('portable Engine smoke must use a clean exact-archive extraction')
            require_hex64(observation.get('fixtureSha256'), 'Engine smoke fixtureSha256')
            require_hex64(observation.get('resultSha256'), 'Engine smoke resultSha256')
            if not isinstance(observation.get('engineVersion'), str) or not observation['engineVersion'].strip():
                raise ValueError('Engine smoke engineVersion is missing')
    elif kind in {'unpacked-extension', 'store-installed-extension'}:
        if observation.get('platform') != 'browser':
            raise ValueError('browser smoke platform must be browser')
        expected = artifacts.get('browser')
        if not isinstance(expected, dict):
            raise ValueError('controlled manifest has no Extension artifact')
        if observation.get('artifact') != expected.get('artifact'):
            raise ValueError('browser smoke artifact name differs from controlled manifest')
        if require_hex64(observation.get('artifactSha256'), 'browser smoke artifactSha256') != require_hex64(expected.get('sha256'), 'controlled Extension sha256'):
            raise ValueError('browser smoke artifact hash differs from controlled manifest')
        engine_target = observation.get('engineTargetAtTest')
        if engine_target not in V1_ENGINE_TARGETS:
            raise ValueError('browser smoke must identify the controlled V1 Engine target used at test time')
        expected_engine = artifacts.get(str(engine_target))
        if not isinstance(expected_engine, dict):
            raise ValueError(f'controlled manifest has no Engine artifact for browser smoke target {engine_target}')
        if observation.get('engineArtifactAtTest') != expected_engine.get('artifact'):
            raise ValueError('browser smoke Engine artifact name differs from controlled manifest')
        if require_hex64(observation.get('engineArtifactSha256AtTest'), 'browser smoke Engine artifact sha256') != require_hex64(expected_engine.get('sha256'), 'controlled Engine sha256'):
            raise ValueError('browser smoke Engine artifact hash differs from controlled manifest')
        browser_version = observation.get('browserVersion')
        if not isinstance(browser_version, str) or not re.fullmatch(r'\d+(?:\.\d+){0,3}', browser_version):
            raise ValueError('browser smoke browserVersion is invalid')
        if kind == 'unpacked-extension' and observation.get('evidenceMode') != 'interactive-human-observed-exact-bytes':
            raise ValueError('unpacked browser smoke must be produced by the interactive exact-byte acceptance flow')
        if kind == 'unpacked-extension' and not isinstance(observation.get('fixtureUrl'), str):
            raise ValueError('unpacked browser smoke fixtureUrl is missing')
        if kind == 'store-installed-extension':
            if observation.get('evidenceMode') != 'interactive-human-observed-store-installed-controlled-candidate':
                raise ValueError('Store-installed browser smoke must use the controlled-candidate acceptance flow')
            require_hex64(observation.get('orchestrationSessionSha256'), 'Store-installed orchestrationSessionSha256')
            require_hex64(observation.get('storeSubmissionHandoffSha256'), 'Store-installed storeSubmissionHandoffSha256')
            require_hex64(observation.get('storeCandidateSha256'), 'Store-installed storeCandidateSha256')
            item_id = observation.get('storeItemId')
            if not isinstance(item_id, str) or not re.fullmatch(r'[a-p]{32}', item_id):
                raise ValueError('Store-installed observation has invalid Chrome Web Store item id')
            store_version = observation.get('storeVersion')
            if not isinstance(store_version, str) or not re.fullmatch(r'\d+(?:\.\d+){0,3}', store_version):
                raise ValueError('Store-installed observation has invalid Store version')
    else:
        raise ValueError('smoke observation kind is unsupported')
    return observation
