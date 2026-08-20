from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'engine'))

from release_evidence import (  # type: ignore
    V1_ENGINE_TARGETS,
    load_json,
    require_hex40,
    require_hex64,
    sha256_file,
    sha256_json,
    validate_controlled_manifest,
    validate_smoke_observation,
)
from mte_engine.benchmark.dependency_locks import dependency_lock_pins  # type: ignore
from mte_engine.benchmark.freeze import load_freeze  # type: ignore
from mte_engine.benchmark.source_binding import verify_current_source_binding  # type: ignore

REVISION = 'rev19-v1-evidence-orchestration-v2-public-store-closure'
STAGES = (
    'qualification-promoted',
    'controlled-assembled',
    'native-smoke-complete',
    'browser-smoke-complete',
    'evidence-promoted',
    'public-evidence-promoted',
    'release-ready',
)


STORE_HANDOFF_REVISION = 'rev19-store-submission-handoff-v1'


class OrchestrationError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('utf-8')


def session_digest(value: dict[str, Any]) -> str:
    body = dict(value)
    body.pop('sessionSha256', None)
    return hashlib.sha256(canonical(body)).hexdigest()


def seal_session(value: dict[str, Any]) -> dict[str, Any]:
    value['sessionSha256'] = session_digest(value)
    return value


def write_session(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(seal_session(value), indent=2) + '\n', encoding='utf-8')


def read_session(path: Path, expected_stage: str | None = None) -> dict[str, Any]:
    value = load_json(path.resolve(), 'V1 orchestration session')
    if value.get('schemaVersion') != 1 or value.get('revision') != REVISION:
        raise OrchestrationError('V1 orchestration session schema/revision is unsupported')
    if value.get('stage') not in STAGES:
        raise OrchestrationError('V1 orchestration session stage is invalid')
    require_hex40(value.get('assemblySourceHeadSha'), 'orchestration assemblySourceHeadSha')
    require_hex40(value.get('qualifiedSourceHeadSha'), 'orchestration qualifiedSourceHeadSha')
    expected = session_digest(value)
    if value.get('sessionSha256') != expected:
        raise OrchestrationError('V1 orchestration session hash does not verify')
    qualification = value.get('qualification')
    if not isinstance(qualification, dict):
        raise OrchestrationError('orchestration qualification payload is missing')
    for key in ('freezeSha256','freezeIdentitySha256','runPlanSha256','packageLockSha256','uvLockSha256'):
        require_hex64(qualification.get(key), f'orchestration qualification.{key}')
    stage_index = STAGES.index(value['stage'])
    if stage_index >= STAGES.index('controlled-assembled'):
        controlled = value.get('controlled')
        if not isinstance(controlled, dict):
            raise OrchestrationError('orchestration controlled payload is missing')
        require_hex64(controlled.get('manifestSha256'), 'orchestration controlled.manifestSha256')
        parse_run_id(str(controlled.get('controlledRunId','')), 'orchestration controlled run id')
        runs = controlled.get('candidateRunIds')
        if not isinstance(runs, dict) or set(runs) != {'extension','linux','macos','windows'} or len(set(runs.values())) != 4:
            raise OrchestrationError('orchestration candidate run-id set is incomplete or non-distinct')
        for label, run_id in runs.items():
            parse_run_id(str(run_id), f'orchestration {label} candidate run id')
    if stage_index >= STAGES.index('native-smoke-complete'):
        native = value.get('nativeSmoke')
        if not isinstance(native, dict):
            raise OrchestrationError('orchestration nativeSmoke payload is missing')
        parse_run_id(str(native.get('engineSmokeRunId','')), 'orchestration Engine smoke run id')
        obs = native.get('observations')
        if not isinstance(obs, dict) or set(obs) != set(V1_ENGINE_TARGETS):
            raise OrchestrationError('orchestration native observation set is incomplete')
        for target, digest in obs.items():
            require_hex64(digest, f'orchestration native observation {target}')
    if stage_index >= STAGES.index('browser-smoke-complete'):
        browser = value.get('browserSmoke')
        obs = browser.get('observationsByMajor') if isinstance(browser, dict) else None
        if not isinstance(obs, dict) or len(obs) != 2:
            raise OrchestrationError('orchestration browser observation set must contain exactly two majors')
        for major, digest in obs.items():
            if not str(major).isdigit():
                raise OrchestrationError('orchestration browser major is invalid')
            require_hex64(digest, f'orchestration browser observation Chrome {major}')
    if stage_index >= STAGES.index('evidence-promoted'):
        promoted = value.get('evidencePromotion')
        if not isinstance(promoted, dict):
            raise OrchestrationError('orchestration evidencePromotion payload is missing')
        for key in ('profilePrivacySha256','smokeRecordsSha256','releaseStateSha256'):
            require_hex64(promoted.get(key), f'orchestration evidencePromotion.{key}')
    if value.get('stage') == 'public-evidence-promoted' and value.get('releaseClass') != 'public-v1':
        raise OrchestrationError('public-evidence-promoted stage is valid only for public-v1')
    if value.get('releaseClass') == 'public-v1' and stage_index >= STAGES.index('public-evidence-promoted'):
        promoted_public = value.get('publicEvidencePromotion')
        if not isinstance(promoted_public, dict):
            raise OrchestrationError('orchestration publicEvidencePromotion payload is missing')
        for key in ('profilePrivacySha256','smokeRecordsSha256','releaseStateSha256','publicationStateSha256','supportChannelsSha256','productionDownloadsSha256','storeCandidateMetadataSha256','storeSubmissionHandoffSha256'):
            require_hex64(promoted_public.get(key), f'orchestration publicEvidencePromotion.{key}')
        store_obs = promoted_public.get('storeInstalledObservationsByMajor')
        if not isinstance(store_obs, dict) or len(store_obs) != 2:
            raise OrchestrationError('public orchestration must bind exactly two Store-installed Chrome observations')
        for major, digest in store_obs.items():
            if not str(major).isdigit():
                raise OrchestrationError('public orchestration Store Chrome major is invalid')
            require_hex64(digest, f'orchestration Store observation Chrome {major}')
    if stage_index >= STAGES.index('release-ready'):
        final_gate = value.get('finalGate')
        if not isinstance(final_gate, dict) or final_gate.get('passed') is not True:
            raise OrchestrationError('orchestration release-ready session lacks a passing final gate')
    if expected_stage is not None and value.get('stage') != expected_stage:
        raise OrchestrationError(f'orchestration stage ordering violation: expected {expected_stage}, got {value.get("stage")}')
    return value


def next_session(previous: dict[str, Any], stage: str, payload_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    current = previous['stage']
    if current == 'evidence-promoted':
        allowed = {'public-evidence-promoted'} if previous.get('releaseClass') == 'public-v1' else {'release-ready'}
    elif current == 'public-evidence-promoted':
        allowed = {'release-ready'}
    else:
        index = STAGES.index(current)
        allowed = {STAGES[index + 1]} if index + 1 < len(STAGES) else set()
    if stage not in allowed:
        raise OrchestrationError(f'cannot advance directly from {current} to {stage}')
    value = dict(previous)
    value['previousSessionSha256'] = previous['sessionSha256']
    value['stage'] = stage
    value['sequence'] = int(previous.get('sequence', 0)) + 1
    value[payload_key] = payload
    value.pop('sessionSha256', None)
    return value


def handoff_digest(value: dict[str, Any]) -> str:
    body = dict(value)
    body.pop('handoffSha256', None)
    return hashlib.sha256(canonical(body)).hexdigest()


def write_store_handoff(path: Path, value: dict[str, Any]) -> None:
    value['handoffSha256'] = handoff_digest(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def read_store_handoff(path: Path) -> dict[str, Any]:
    value = load_json(path.resolve(), 'Store submission handoff')
    if value.get('schemaVersion') != 1 or value.get('revision') != STORE_HANDOFF_REVISION:
        raise OrchestrationError('Store submission handoff schema/revision is unsupported')
    if value.get('releaseClass') != 'public-v1' or value.get('gatePassed') is not True:
        raise OrchestrationError('Store submission handoff is not a passing public-v1 pre-Store gate')
    require_hex40(value.get('assemblySourceHeadSha'), 'Store handoff assemblySourceHeadSha')
    require_hex40(value.get('qualifiedSourceHeadSha'), 'Store handoff qualifiedSourceHeadSha')
    for key in ('orchestrationSessionSha256','controlledManifestSha256','extensionSha256'):
        require_hex64(value.get(key), f'Store handoff {key}')
    if value.get('handoffSha256') != handoff_digest(value):
        raise OrchestrationError('Store submission handoff hash does not verify')
    return value


def require_release_identity(session: dict[str, Any], manifest: dict[str, Any], manifest_sha: str) -> None:
    if manifest.get('releaseId') != session.get('releaseId'):
        raise OrchestrationError('controlled manifest releaseId differs from orchestration session')
    if manifest.get('releaseClass') != session.get('releaseClass'):
        raise OrchestrationError('controlled manifest releaseClass differs from orchestration session')
    if manifest.get('sourceHeadSha') != session.get('assemblySourceHeadSha'):
        raise OrchestrationError('controlled manifest assembly source commit differs from orchestration session')
    if manifest.get('qualifiedSourceHeadSha') != session.get('qualifiedSourceHeadSha'):
        raise OrchestrationError('controlled manifest qualified source commit differs from orchestration session')
    controlled = session.get('controlled')
    if isinstance(controlled, dict) and controlled.get('manifestSha256') != manifest_sha:
        raise OrchestrationError('controlled manifest bytes differ from the previously sealed orchestration stage')


def cmd_init(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    freeze_path = (root / 'engine/mte_engine/benchmark/production-profile-freeze.json').resolve()
    freeze = load_freeze(freeze_path)
    if freeze is None:
        raise OrchestrationError('a valid promoted production-profile-freeze.json is required before orchestration starts')
    verify_current_source_binding(root, freeze.get('qualifiedSource'))
    locks = dependency_lock_pins(root)
    if freeze.get('dependencyLocks') != locks:
        raise OrchestrationError('current dependency locks differ from the production freeze')
    qualified = (freeze.get('qualifiedSource') or {}).get('sourceHeadSha')
    require_hex40(qualified, 'production freeze qualifiedSource.sourceHeadSha')
    assembly = require_hex40(args.assembly_source_head_sha, 'assembly source head sha')
    release_class = args.release_class
    if release_class not in {'private-v1', 'public-v1'}:
        raise OrchestrationError('V1 orchestration accepts only private-v1/public-v1')
    value = {
        'schemaVersion': 1,
        'revision': REVISION,
        'releaseId': args.release_id,
        'releaseClass': release_class,
        'stage': 'qualification-promoted',
        'sequence': 1,
        'assemblySourceHeadSha': assembly,
        'qualifiedSourceHeadSha': qualified,
        'qualification': {
            'freezeSha256': sha256_file(freeze_path),
            'freezeIdentitySha256': require_hex64(freeze.get('freezeSha256'), 'freeze freezeSha256'),
            'runPlanSha256': require_hex64(freeze.get('runPlanSha256'), 'freeze runPlanSha256'),
            'packageLockSha256': require_hex64(locks.get('packageLockSha256'), 'package lock sha256'),
            'uvLockSha256': require_hex64(locks.get('uvLockSha256'), 'uv lock sha256'),
        },
        'previousSessionSha256': None,
    }
    write_session(args.output.resolve(), value)
    print(json.dumps(value | {'sessionSha256': session_digest(value)}, indent=2))
    return 0


def parse_run_id(value: str, label: str) -> int:
    if not value.isdigit() or int(value) <= 0:
        raise OrchestrationError(f'{label} must be a positive GitHub Actions run id')
    return int(value)


def cmd_controlled(args: argparse.Namespace) -> int:
    previous = read_session(args.session, 'qualification-promoted')
    manifest, manifest_sha = validate_controlled_manifest(args.controlled_manifest.resolve(), require_v1=True)
    require_release_identity(previous, manifest, manifest_sha)
    freeze_meta = next((x for x in manifest.get('metadata', []) if isinstance(x, dict) and x.get('artifact') == 'production-profile-freeze.json'), None)
    if not isinstance(freeze_meta, dict) or require_hex64(freeze_meta.get('sha256'), 'controlled freeze sha256') != previous['qualification']['freezeSha256']:
        raise OrchestrationError('controlled archive does not carry the exact promoted production freeze bytes')
    candidate_runs = {
        'extension': parse_run_id(args.extension_run_id, 'extension run id'),
        'linux': parse_run_id(args.linux_run_id, 'Linux run id'),
        'macos': parse_run_id(args.macos_run_id, 'macOS run id'),
        'windows': parse_run_id(args.windows_run_id, 'Windows run id'),
    }
    if len(set(candidate_runs.values())) != 4:
        raise OrchestrationError('candidate workflow run ids must be distinct')
    payload = {
        'manifestSha256': manifest_sha,
        'controlledRunId': parse_run_id(args.controlled_run_id, 'controlled release run id'),
        'candidateRunIds': candidate_runs,
    }
    value = next_session(previous, 'controlled-assembled', 'controlled', payload)
    write_session(args.output.resolve(), value)
    print(json.dumps(seal_session(value), indent=2))
    return 0


def cmd_native(args: argparse.Namespace) -> int:
    previous = read_session(args.session, 'controlled-assembled')
    manifest, manifest_sha = validate_controlled_manifest(args.controlled_manifest.resolve(), require_v1=True)
    require_release_identity(previous, manifest, manifest_sha)
    observations: dict[str, str] = {}
    for path in args.engine_observation:
        item = load_json(path.resolve(), f'Engine observation {path}')
        validate_smoke_observation(item, manifest=manifest, manifest_sha256=manifest_sha)
        target = item.get('platform')
        if target in observations:
            raise OrchestrationError(f'duplicate Engine smoke target: {target}')
        observations[str(target)] = sha256_json(item)
    if set(observations) != set(V1_ENGINE_TARGETS):
        raise OrchestrationError('native smoke stage requires exactly Linux, macOS and Windows observations')
    payload = {
        'engineSmokeRunId': parse_run_id(args.engine_smoke_run_id, 'Engine smoke run id'),
        'observations': dict(sorted(observations.items())),
    }
    value = next_session(previous, 'native-smoke-complete', 'nativeSmoke', payload)
    write_session(args.output.resolve(), value)
    print(json.dumps(seal_session(value), indent=2))
    return 0


def browser_major(version: str) -> int:
    return int(version.split('.', 1)[0])


def cmd_browser(args: argparse.Namespace) -> int:
    previous = read_session(args.session, 'native-smoke-complete')
    manifest, manifest_sha = validate_controlled_manifest(args.controlled_manifest.resolve(), require_v1=True)
    require_release_identity(previous, manifest, manifest_sha)
    state = load_json(args.release_state.resolve(), 'release state')
    audit = state.get('audit') if isinstance(state.get('audit'), dict) else {}
    required = {int(audit.get('chromeBaselineMajor', 0)), int(audit.get('currentStableMajorAtAudit', 0))}
    if 0 in required or len(required) != 2:
        raise OrchestrationError('release-state audit must define distinct Chrome baseline and current Stable majors')
    observations: dict[int, str] = {}
    for path in args.browser_observation:
        item = load_json(path.resolve(), f'browser observation {path}')
        validate_smoke_observation(item, manifest=manifest, manifest_sha256=manifest_sha)
        if item.get('kind') != 'unpacked-extension':
            raise OrchestrationError('V1 browser stage accepts only unpacked-extension exact-byte observations')
        if item.get('orchestrationSessionSha256') != previous.get('sessionSha256'):
            raise OrchestrationError('browser observation is not bound to the native-smoke orchestration checkpoint')
        major = browser_major(str(item.get('browserVersion')))
        if major in observations:
            raise OrchestrationError(f'duplicate browser smoke major: {major}')
        observations[major] = sha256_json(item)
    if set(observations) != required:
        raise OrchestrationError(f'browser smoke stage requires exactly Chrome majors {sorted(required)}')
    payload = {'observationsByMajor': {str(k): v for k, v in sorted(observations.items())}}
    value = next_session(previous, 'browser-smoke-complete', 'browserSmoke', payload)
    write_session(args.output.resolve(), value)
    print(json.dumps(seal_session(value), indent=2))
    return 0


def cmd_promoted(args: argparse.Namespace) -> int:
    previous = read_session(args.session, 'browser-smoke-complete')
    manifest, manifest_sha = validate_controlled_manifest(args.controlled_manifest.resolve(), require_v1=True)
    require_release_identity(previous, manifest, manifest_sha)
    privacy = load_json(args.profile_privacy.resolve(), 'profile/privacy evidence')
    records = load_json(args.smoke_records.resolve(), 'smoke records')
    state = load_json(args.release_state.resolve(), 'release state')
    if privacy.get('materializedFromControlledManifestSha256') != manifest_sha:
        raise OrchestrationError('profile/privacy evidence is not bound to this controlled manifest')
    if records.get('controlledManifestSha256') != manifest_sha or records.get('sourceHeadSha') != manifest.get('sourceHeadSha'):
        raise OrchestrationError('smoke records are not bound to this controlled manifest/source commit')
    record_items = records.get('records')
    if not isinstance(record_items, list) or len(record_items) < 5:
        raise OrchestrationError('promoted smoke records do not contain the complete V1 evidence set')
    native_hashes: dict[str, str] = {}
    browser_hashes: dict[str, str] = {}
    native_count = 0
    browser_count = 0
    for item in record_items:
        if not isinstance(item, dict):
            raise OrchestrationError('promoted smoke record entry is malformed')
        if item.get('kind') == 'engine-artifact':
            native_count += 1
            native_hashes[str(item.get('platform'))] = sha256_json(item)
        elif item.get('kind') == 'unpacked-extension':
            browser_count += 1
            browser_hashes[str(browser_major(str(item.get('browserVersion'))))] = sha256_json(item)
    if native_count != 3 or browser_count != 2:
        raise OrchestrationError('promoted smoke records must contain exactly three Engine and two unpacked-browser observations')
    if native_hashes != previous['nativeSmoke']['observations']:
        raise OrchestrationError('promoted Engine smoke records differ from the orchestration native checkpoint')
    if browser_hashes != previous['browserSmoke']['observationsByMajor']:
        raise OrchestrationError('promoted browser smoke records differ from the orchestration browser checkpoint')
    artifacts = state.get('artifacts') if isinstance(state.get('artifacts'), dict) else {}
    if state.get('releaseClass') != previous.get('releaseClass') or not isinstance(artifacts.get('controlledManifest'), str):
        raise OrchestrationError('release state was not promoted from the controlled V1 evidence set')
    payload = {
        'profilePrivacySha256': sha256_file(args.profile_privacy.resolve()),
        'smokeRecordsSha256': sha256_file(args.smoke_records.resolve()),
        'releaseStateSha256': sha256_file(args.release_state.resolve()),
    }
    value = next_session(previous, 'evidence-promoted', 'evidencePromotion', payload)
    write_session(args.output.resolve(), value)
    print(json.dumps(seal_session(value), indent=2))
    return 0



def cmd_store_handoff(args: argparse.Namespace) -> int:
    previous = read_session(args.session, 'evidence-promoted')
    if previous.get('releaseClass') != 'public-v1':
        raise OrchestrationError('Store submission handoff is valid only for a public-v1 orchestration session')
    manifest, manifest_sha = validate_controlled_manifest(args.controlled_manifest.resolve(), require_v1=True)
    require_release_identity(previous, manifest, manifest_sha)
    command = [
        sys.executable, str(ROOT / 'scripts/verify_controlled_release_ready.py'),
        '--root', str(args.root.resolve()), '--target-class', 'public-v1', '--gate-stage', 'store-candidate',
    ]
    result = subprocess.run(command, cwd=args.root.resolve(), text=True, capture_output=True)
    if result.returncode != 0:
        detail = (result.stdout + result.stderr).strip()
        raise OrchestrationError('pre-Store public V1 gate is not green; Store candidate handoff refused' + (f': {detail}' if detail else ''))
    extension = manifest.get('extension') if isinstance(manifest.get('extension'), dict) else None
    if not isinstance(extension, dict):
        raise OrchestrationError('controlled manifest Extension entry is missing')
    value = {
        'schemaVersion': 1,
        'revision': STORE_HANDOFF_REVISION,
        'releaseId': previous['releaseId'],
        'releaseClass': 'public-v1',
        'assemblySourceHeadSha': previous['assemblySourceHeadSha'],
        'qualifiedSourceHeadSha': previous['qualifiedSourceHeadSha'],
        'orchestrationSessionSha256': previous['sessionSha256'],
        'controlledManifestSha256': manifest_sha,
        'extensionArtifact': extension.get('artifact'),
        'extensionSha256': require_hex64(extension.get('sha256'), 'controlled Extension sha256'),
        'gate': 'check:controlled-release-ready --gate-stage store-candidate',
        'gatePassed': True,
    }
    write_store_handoff(args.output.resolve(), value)
    print(json.dumps(value | {'handoffSha256': handoff_digest(value)}, indent=2))
    return 0


def cmd_public_promoted(args: argparse.Namespace) -> int:
    previous = read_session(args.session, 'evidence-promoted')
    if previous.get('releaseClass') != 'public-v1':
        raise OrchestrationError('post-Store public evidence promotion is valid only for public-v1')
    manifest, manifest_sha = validate_controlled_manifest(args.controlled_manifest.resolve(), require_v1=True)
    require_release_identity(previous, manifest, manifest_sha)
    privacy = load_json(args.profile_privacy.resolve(), 'profile/privacy evidence')
    records = load_json(args.smoke_records.resolve(), 'smoke records')
    state = load_json(args.release_state.resolve(), 'release state')
    publication = load_json(args.publication_state.resolve(), 'Store publication state')
    handoff = read_store_handoff(args.store_handoff.resolve())
    candidate = load_json(args.store_candidate.resolve(), 'Store candidate metadata')
    if handoff.get('orchestrationSessionSha256') != previous.get('sessionSha256') or handoff.get('controlledManifestSha256') != manifest_sha:
        raise OrchestrationError('Store handoff is not bound to this evidence-promoted session/controlled manifest')
    if candidate.get('controlledManifestSha256') != manifest_sha or candidate.get('storeSubmissionHandoffSha256') != handoff.get('handoffSha256'):
        raise OrchestrationError('Store candidate metadata is not bound to the approved Store handoff')
    extension = manifest.get('extension') if isinstance(manifest.get('extension'), dict) else {}
    if require_hex64(candidate.get('sha256'), 'Store candidate sha256') != require_hex64(extension.get('sha256'), 'controlled Extension sha256'):
        raise OrchestrationError('Store candidate bytes differ from the controlled Extension')
    if privacy.get('materializedFromControlledManifestSha256') != manifest_sha:
        raise OrchestrationError('public profile/privacy evidence is not bound to this controlled manifest')
    if records.get('controlledManifestSha256') != manifest_sha:
        raise OrchestrationError('public smoke records are not bound to this controlled manifest')
    items = records.get('records')
    if not isinstance(items, list):
        raise OrchestrationError('public smoke records are malformed')
    native_hashes: dict[str, str] = {}
    unpacked_hashes: dict[str, str] = {}
    store_hashes: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            raise OrchestrationError('public smoke record entry is malformed')
        validate_smoke_observation(item, manifest=manifest, manifest_sha256=manifest_sha)
        if item.get('kind') == 'engine-artifact':
            native_hashes[str(item.get('platform'))] = sha256_json(item)
        elif item.get('kind') == 'unpacked-extension':
            unpacked_hashes[str(browser_major(str(item.get('browserVersion'))))] = sha256_json(item)
        elif item.get('kind') == 'store-installed-extension':
            major = str(browser_major(str(item.get('browserVersion'))))
            if item.get('storeSubmissionHandoffSha256') != handoff.get('handoffSha256') or item.get('storeCandidateSha256') != candidate.get('sha256'):
                raise OrchestrationError(f'Store-installed observation Chrome {major} is not bound to the approved Store candidate')
            store_hashes[major] = sha256_json(item)
    if native_hashes != previous['nativeSmoke']['observations']:
        raise OrchestrationError('post-Store Engine records differ from the pre-Store orchestration checkpoint')
    if unpacked_hashes != previous['browserSmoke']['observationsByMajor']:
        raise OrchestrationError('post-Store unpacked-browser records differ from the pre-Store orchestration checkpoint')
    audit = state.get('audit') if isinstance(state.get('audit'), dict) else {}
    required_majors = {str(int(audit.get('chromeBaselineMajor', 0))), str(int(audit.get('currentStableMajorAtAudit', 0)))}
    if '0' in required_majors or len(required_majors) != 2 or set(store_hashes) != required_majors:
        raise OrchestrationError(f'post-Store evidence requires exactly Store-installed Chrome majors {sorted(required_majors)}')
    smoke = state.get('smoke') if isinstance(state.get('smoke'), dict) else {}
    gates = publication.get('releaseGates') if isinstance(publication.get('releaseGates'), dict) else {}
    if smoke.get('storeInstalledVersionPassed') is not True:
        raise OrchestrationError('release state does not mirror the validated Store-installed smoke evidence')
    if gates.get('chrome148StoreSmokePassed') is not True or gates.get('currentStableStoreSmokePassed') is not True:
        raise OrchestrationError('Store publication state does not mirror both Store-installed browser observations')
    payload = {
        'profilePrivacySha256': sha256_file(args.profile_privacy.resolve()),
        'smokeRecordsSha256': sha256_file(args.smoke_records.resolve()),
        'releaseStateSha256': sha256_file(args.release_state.resolve()),
        'publicationStateSha256': sha256_file(args.publication_state.resolve()),
        'supportChannelsSha256': sha256_file(args.support_channels.resolve()),
        'productionDownloadsSha256': sha256_file(args.production_downloads.resolve()),
        'storeCandidateMetadataSha256': sha256_file(args.store_candidate.resolve()),
        'storeSubmissionHandoffSha256': handoff['handoffSha256'],
        'storeInstalledObservationsByMajor': dict(sorted(store_hashes.items())),
    }
    value = next_session(previous, 'public-evidence-promoted', 'publicEvidencePromotion', payload)
    write_session(args.output.resolve(), value)
    print(json.dumps(seal_session(value), indent=2))
    return 0

def cmd_finalize(args: argparse.Namespace) -> int:
    previous = read_session(args.session)
    expected = 'public-evidence-promoted' if previous.get('releaseClass') == 'public-v1' else 'evidence-promoted'
    if previous.get('stage') != expected:
        raise OrchestrationError(f'finalization requires {expected}, got {previous.get("stage")}')
    command = [sys.executable, str(ROOT / 'scripts/verify_controlled_release_ready.py'), '--root', str(args.root.resolve()), '--target-class', previous['releaseClass'], '--gate-stage', 'final']
    result = subprocess.run(command, cwd=args.root.resolve(), text=True, capture_output=True)
    if result.returncode != 0:
        detail = (result.stdout + result.stderr).strip()
        raise OrchestrationError('final controlled release gate is not green; orchestration cannot finalize' + (f': {detail}' if detail else ''))
    payload = {'gate': 'check:controlled-release-ready', 'targetClass': previous['releaseClass'], 'passed': True}
    value = next_session(previous, 'release-ready', 'finalGate', payload)
    write_session(args.output.resolve(), value)
    print(json.dumps(seal_session(value), indent=2))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    value = read_session(args.session)
    print(json.dumps({'valid': True, 'stage': value['stage'], 'sequence': value['sequence'], 'sessionSha256': value['sessionSha256']}, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Fail-closed V1 evidence orchestration state machine.')
    sub = p.add_subparsers(dest='command', required=True)
    q = sub.add_parser('init'); q.add_argument('--root', type=Path, default=ROOT); q.add_argument('--release-id', required=True); q.add_argument('--release-class', choices=['private-v1','public-v1'], required=True); q.add_argument('--assembly-source-head-sha', required=True); q.add_argument('--output', type=Path, required=True); q.set_defaults(func=cmd_init)
    q = sub.add_parser('controlled'); q.add_argument('--session', type=Path, required=True); q.add_argument('--controlled-manifest', type=Path, required=True); q.add_argument('--controlled-run-id', required=True); q.add_argument('--extension-run-id', required=True); q.add_argument('--linux-run-id', required=True); q.add_argument('--macos-run-id', required=True); q.add_argument('--windows-run-id', required=True); q.add_argument('--output', type=Path, required=True); q.set_defaults(func=cmd_controlled)
    q = sub.add_parser('native'); q.add_argument('--session', type=Path, required=True); q.add_argument('--controlled-manifest', type=Path, required=True); q.add_argument('--engine-smoke-run-id', required=True); q.add_argument('--engine-observation', type=Path, action='append', default=[]); q.add_argument('--output', type=Path, required=True); q.set_defaults(func=cmd_native)
    q = sub.add_parser('browser'); q.add_argument('--session', type=Path, required=True); q.add_argument('--controlled-manifest', type=Path, required=True); q.add_argument('--release-state', type=Path, default=ROOT/'release-control/release-state.json'); q.add_argument('--browser-observation', type=Path, action='append', default=[]); q.add_argument('--output', type=Path, required=True); q.set_defaults(func=cmd_browser)
    q = sub.add_parser('promoted'); q.add_argument('--session', type=Path, required=True); q.add_argument('--controlled-manifest', type=Path, required=True); q.add_argument('--profile-privacy', type=Path, default=ROOT/'store/release/profile-privacy.json'); q.add_argument('--smoke-records', type=Path, default=ROOT/'release-control/smoke-records.json'); q.add_argument('--release-state', type=Path, default=ROOT/'release-control/release-state.json'); q.add_argument('--output', type=Path, required=True); q.set_defaults(func=cmd_promoted)
    q = sub.add_parser('store-handoff'); q.add_argument('--root', type=Path, default=ROOT); q.add_argument('--session', type=Path, required=True); q.add_argument('--controlled-manifest', type=Path, required=True); q.add_argument('--output', type=Path, required=True); q.set_defaults(func=cmd_store_handoff)
    q = sub.add_parser('public-promoted'); q.add_argument('--session', type=Path, required=True); q.add_argument('--controlled-manifest', type=Path, required=True); q.add_argument('--profile-privacy', type=Path, default=ROOT/'store/release/profile-privacy.json'); q.add_argument('--smoke-records', type=Path, default=ROOT/'release-control/smoke-records.json'); q.add_argument('--release-state', type=Path, default=ROOT/'release-control/release-state.json'); q.add_argument('--publication-state', type=Path, default=ROOT/'store/publication-state.json'); q.add_argument('--support-channels', type=Path, default=ROOT/'release-control/support-channels.json'); q.add_argument('--production-downloads', type=Path, default=ROOT/'release-control/production-downloads.json'); q.add_argument('--store-candidate', type=Path, required=True); q.add_argument('--store-handoff', type=Path, required=True); q.add_argument('--output', type=Path, required=True); q.set_defaults(func=cmd_public_promoted)
    q = sub.add_parser('finalize'); q.add_argument('--root', type=Path, default=ROOT); q.add_argument('--session', type=Path, required=True); q.add_argument('--output', type=Path, required=True); q.set_defaults(func=cmd_finalize)
    q = sub.add_parser('verify'); q.add_argument('--session', type=Path, required=True); q.set_defaults(func=cmd_verify)
    return p


def main() -> int:
    args = parser().parse_args()
    return args.func(args)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OrchestrationError, ValueError, OSError) as exc:
        print(f'V1 evidence orchestration failed closed: {exc}', file=sys.stderr)
        raise SystemExit(2)
