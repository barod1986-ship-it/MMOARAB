from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib.util
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RECOVERY_TOOL = ROOT / 'scripts' / 'first_real_run_recovery.py'
DEFAULT_CONTRACT = ROOT / 'release-control' / 'production-execution-contract.json'
ROTATION_REVISION = 'rev34-recovery-rotation-v1'
STATE_REVISION = 'rev34-recovery-rotation-state-v1'
RECEIPT_REVISION = 'rev34-recovery-copy-receipt-v1'
DEFAULT_KEY_ENV = 'MTE_RECOVERY_ROTATION_HMAC_KEY'


class RotationError(ValueError):
    pass


def load_recovery():
    spec = importlib.util.spec_from_file_location('mte_recovery_for_rotation', RECOVERY_TOOL)
    if spec is None or spec.loader is None:
        raise RotationError('could not load recovery module')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = load_recovery()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def sha256_file(path: Path) -> str:
    return R.sha256_file(path)


def file_sha_and_size(path: Path) -> tuple[str, int]:
    return sha256_file(path), path.stat().st_size


def _hash_without(value: dict[str, Any], field: str) -> str:
    body = dict(value)
    body.pop(field, None)
    return hashlib.sha256(canonical(body)).hexdigest()


def seal_config(value: dict[str, Any]) -> dict[str, Any]:
    value = json.loads(json.dumps(value))
    value['configSha256'] = _hash_without(value, 'configSha256')
    return value


def validate_config(value: dict[str, Any]) -> dict[str, Any]:
    if value.get('schemaVersion') != 1 or value.get('revision') != ROTATION_REVISION:
        raise RotationError('unsupported recovery rotation config schema/revision')
    if value.get('configSha256') != _hash_without(value, 'configSha256'):
        raise RotationError('recovery rotation configSha256 mismatch; use init-config/set-destination rather than editing a sealed config manually')
    release_id = str(value.get('releaseId', '')).strip()
    if not release_id:
        raise RotationError('rotation config releaseId is required')
    policy = value.get('policy') if isinstance(value.get('policy'), dict) else {}
    if int(policy.get('minimumCopiesPerGeneration', 0)) < 2:
        raise RotationError('rotation policy must require at least two copies per generation')
    if int(policy.get('minimumRetainedGenerations', 0)) < 2:
        raise RotationError('rotation policy must retain at least two complete generations')
    if policy.get('requireRestoreProbeBeforeActivation') is not True:
        raise RotationError('rotation policy must require a real restore probe before activating a generation')
    destinations = value.get('destinations')
    if not isinstance(destinations, list):
        raise RotationError('rotation destinations must be an array')
    ids: set[str] = set()
    roots: list[Path] = []
    offsite = 0
    for item in destinations:
        if not isinstance(item, dict):
            raise RotationError('rotation destination entry is invalid')
        storage_id = str(item.get('storageId', '')).strip()
        role = str(item.get('role', '')).strip()
        root = Path(str(item.get('root', ''))).expanduser()
        if not storage_id or storage_id in ids:
            raise RotationError('rotation storageId values must be non-empty and unique')
        if role not in {'primary', 'offsite'}:
            raise RotationError('rotation destination role must be primary or offsite')
        if not root.is_absolute():
            raise RotationError(f'rotation destination root must be absolute: {root}')
        resolved = root.resolve()
        if resolved == ROOT.resolve() or ROOT.resolve() in resolved.parents or resolved in ROOT.resolve().parents:
            raise RotationError('rotation destinations must be outside the source checkout')
        for other in roots:
            if resolved == other or resolved in other.parents or other in resolved.parents:
                raise RotationError('rotation destination roots must not overlap/nest each other')
        roots.append(resolved)
        ids.add(storage_id)
        if role == 'offsite' and item.get('offsiteDeclared') is True:
            offsite += 1
    if len(destinations) < int(policy['minimumCopiesPerGeneration']):
        raise RotationError('rotation config has fewer destinations than minimumCopiesPerGeneration')
    if policy.get('requireOffsiteDeclaredCopy') is True and offsite < 1:
        raise RotationError('rotation policy requires at least one destination explicitly declared offsite')
    return value


def load_config(path: Path) -> dict[str, Any]:
    return validate_config(json.loads(path.read_text(encoding='utf-8')))


def _key_from_env(env_name: str) -> bytes:
    raw = os.environ.get(env_name, '')
    if len(raw.encode('utf-8')) < 32:
        raise RotationError(f'{env_name} must be present and contain at least 32 bytes; keep this local/offline and out of repository secrets')
    return raw.encode('utf-8')


def _hmac_value(value: dict[str, Any], key: bytes, field: str) -> str:
    body = dict(value)
    body.pop(field, None)
    return hmac.new(key, canonical(body), hashlib.sha256).hexdigest()


def _sign(value: dict[str, Any], key: bytes, field: str) -> dict[str, Any]:
    value = json.loads(json.dumps(value))
    value[field] = _hmac_value(value, key, field)
    return value


def _verify_signature(value: dict[str, Any], key: bytes, field: str, label: str) -> None:
    actual = str(value.get(field, ''))
    expected = _hmac_value(value, key, field)
    if not actual or not hmac.compare_digest(actual, expected):
        raise RotationError(f'{label} HMAC-SHA256 mismatch')


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(value, f, indent=2, sort_keys=True, ensure_ascii=False)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
        try:
            dfd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise


def _initial_state(config: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    return {
        'schemaVersion': 1,
        'revision': STATE_REVISION,
        'releaseId': ledger['releaseId'],
        'releaseClass': ledger['releaseClass'],
        'repository': ledger['repository'],
        'repositoryId': str(ledger['repositoryId']),
        'configSha256': config['configSha256'],
        'generations': [],
        'retiredGenerations': [],
        'activeGenerationId': None,
        'updatedAt': now_iso(),
        'notice': 'Operational backup-rotation state only. It preserves recovery durability and never satisfies a release/qualification/smoke gate.',
    }


def load_state(path: Path, config: dict[str, Any], ledger: dict[str, Any], key: bytes, *, allow_missing: bool = False) -> dict[str, Any]:
    if not path.exists():
        if allow_missing:
            return _initial_state(config, ledger)
        raise RotationError(f'rotation state is missing: {path}')
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('schemaVersion') != 1 or value.get('revision') != STATE_REVISION:
        raise RotationError('unsupported rotation state schema/revision')
    _verify_signature(value, key, 'stateHmacSha256', 'rotation state')
    if value.get('configSha256') != config['configSha256']:
        raise RotationError('rotation state belongs to a different sealed rotation config')
    for field in ['releaseId', 'releaseClass', 'repository']:
        if str(value.get(field)) != str(ledger.get(field)):
            raise RotationError(f'rotation state {field} differs from the current ledger')
    if str(value.get('repositoryId')) != str(ledger.get('repositoryId')):
        raise RotationError('rotation state repositoryId differs from the current ledger')
    if not isinstance(value.get('generations'), list) or not isinstance(value.get('retiredGenerations'), list):
        raise RotationError('rotation state generation arrays are invalid')
    return value


def _state_sign_write(path: Path, value: dict[str, Any], key: bytes) -> dict[str, Any]:
    value = json.loads(json.dumps(value))
    value['updatedAt'] = now_iso()
    value = _sign(value, key, 'stateHmacSha256')
    _atomic_json(path, value)
    return value


def _generation_dir(destination: dict[str, Any], release_id: str, generation_id: str) -> Path:
    return Path(str(destination['root'])).expanduser().resolve() / R.safe_name(release_id) / generation_id


def _make_receipt(*, destination: dict[str, Any], generation_id: str, bundle: Path, bundle_manifest: dict[str, Any], ledger_sha: str, key: bytes) -> dict[str, Any]:
    bundle_sha, size = file_sha_and_size(bundle)
    root = Path(str(destination['root'])).expanduser().resolve()
    try:
        device = str(root.stat().st_dev)
    except OSError:
        device = 'unknown'
    receipt = {
        'schemaVersion': 1,
        'revision': RECEIPT_REVISION,
        'generationId': generation_id,
        'releaseId': bundle_manifest['releaseId'],
        'storageId': destination['storageId'],
        'role': destination['role'],
        'offsiteDeclared': bool(destination.get('offsiteDeclared')),
        'storageRoot': str(root),
        'filesystemDevice': device,
        'bundleFile': 'recovery.zip',
        'bundleSha256': bundle_sha,
        'bundleSizeBytes': size,
        'bundleManifestSha256': bundle_manifest['manifestSha256'],
        'ledgerSha256': ledger_sha,
        'copiedAt': now_iso(),
    }
    return _sign(receipt, key, 'receiptHmacSha256')


def _verify_receipt(receipt: dict[str, Any], destination: dict[str, Any], generation: dict[str, Any], key: bytes) -> Path:
    if receipt.get('schemaVersion') != 1 or receipt.get('revision') != RECEIPT_REVISION:
        raise RotationError('copy receipt schema/revision is invalid')
    _verify_signature(receipt, key, 'receiptHmacSha256', f'copy receipt {destination["storageId"]}')
    if str(receipt.get('generationId')) != str(generation.get('generationId')) or str(receipt.get('storageId')) != str(destination['storageId']):
        raise RotationError('copy receipt generation/storage identity mismatch')
    if str(receipt.get('bundleSha256')) != str(generation.get('bundleSha256')) or str(receipt.get('ledgerSha256')) != str(generation.get('ledgerSha256')):
        raise RotationError('copy receipt bundle/ledger identity mismatch')
    generation_dir = _generation_dir(destination, str(generation['releaseId']), str(generation['generationId']))
    bundle = generation_dir / 'recovery.zip'
    if not bundle.is_file() or bundle.is_symlink():
        raise RotationError(f'backup copy missing or symlinked for storage {destination["storageId"]}')
    if bundle.stat().st_size != int(receipt.get('bundleSizeBytes', -1)) or sha256_file(bundle) != str(receipt.get('bundleSha256')):
        raise RotationError(f'backup copy bytes differ from signed receipt for storage {destination["storageId"]}')
    verified = R.verify_bundle(bundle)
    if str(verified.get('manifestSha256')) != str(receipt.get('bundleManifestSha256')):
        raise RotationError('backup copy recovery manifest differs from signed receipt')
    if str(verified.get('originalLedgerSha256')) != str(generation.get('ledgerSha256')):
        raise RotationError('backup copy recovery bundle is bound to a different operational ledger')
    if str(verified.get('releaseId')) != str(generation.get('releaseId')):
        raise RotationError('backup copy recovery bundle releaseId differs from the rotation generation')
    return bundle


def _copy_to_destination(bundle: Path, destination: dict[str, Any], generation_id: str, bundle_manifest: dict[str, Any], ledger_sha: str, key: bytes) -> dict[str, Any]:
    final = _generation_dir(destination, str(bundle_manifest['releaseId']), generation_id)
    final.parent.mkdir(parents=True, exist_ok=True)
    if final.exists():
        receipt_path = final / 'COPY_RECEIPT.json'
        if not receipt_path.is_file():
            raise RotationError(f'existing generation directory has no receipt: {final}')
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        fake_generation = {'generationId': generation_id, 'releaseId': bundle_manifest['releaseId'], 'bundleSha256': sha256_file(bundle), 'ledgerSha256': ledger_sha}
        _verify_receipt(receipt, destination, fake_generation, key)
        return receipt
    staging = Path(tempfile.mkdtemp(prefix=f'.{generation_id}.staging-', dir=final.parent))
    try:
        target_bundle = staging / 'recovery.zip'
        with bundle.open('rb') as src, target_bundle.open('wb') as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        if sha256_file(target_bundle) != sha256_file(bundle):
            raise RotationError(f'backup copy SHA-256 mismatch during copy to {destination["storageId"]}')
        verified = R.verify_bundle(target_bundle)
        if verified.get('manifestSha256') != bundle_manifest['manifestSha256']:
            raise RotationError('backup copy manifest differs after copy')
        receipt = _make_receipt(destination=destination, generation_id=generation_id, bundle=target_bundle, bundle_manifest=bundle_manifest, ledger_sha=ledger_sha, key=key)
        _atomic_json(staging / 'COPY_RECEIPT.json', receipt)
        os.replace(staging, final)
        return receipt
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _propagate_state(state: dict[str, Any], config: dict[str, Any]) -> None:
    for generation in state.get('generations') or []:
        for copy in generation.get('copies') or []:
            destination = next((x for x in config['destinations'] if x['storageId'] == copy['storageId']), None)
            if destination is None:
                continue
            target = _generation_dir(destination, state['releaseId'], generation['generationId']) / 'ROTATION_STATE.json'
            if target.parent.is_dir():
                _atomic_json(target, state)


def _bundle_manifest(bundle: Path) -> dict[str, Any]:
    temp = Path(tempfile.mkdtemp(prefix='.mte-rotation-inspect.'))
    try:
        R._safe_extract_bundle(bundle.resolve(), temp)
        return R._verify_extracted_bundle(temp, bundle.resolve())
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def _restore_probe(bundle: Path, restore_checkout: Path, generation_id: str) -> dict[str, Any]:
    output = Path('release') / 'rotation-probes' / generation_id
    result = R.restore_bundle(bundle=bundle, checkout=restore_checkout.resolve(), output=output)
    root = Path(str(result['restoreRoot']))
    try:
        verified = R.verify_restored(checkout=restore_checkout.resolve(), restore_root=root)
        return {
            'passed': True,
            'storageBundleSha256': sha256_file(bundle),
            'restoreManifestSha256': verified['restoreManifestSha256'],
            'nextStage': verified['nextStage'],
            'verifiedAt': now_iso(),
        }
    finally:
        # Probe output is disposable operational material. The signed generation record preserves the result.
        shutil.rmtree(root, ignore_errors=True)
        parent = root.parent
        try:
            parent.rmdir()
        except OSError:
            pass


def rotate(*, ledger_path: Path, contract_path: Path, bundle: Path, config_path: Path, state_path: Path, restore_checkout: Path, key_env: str) -> dict[str, Any]:
    ledger_path = ledger_path.resolve()
    bundle = bundle.resolve()
    config = load_config(config_path.resolve())
    key = _key_from_env(key_env)
    ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
    contract = json.loads(contract_path.resolve().read_text(encoding='utf-8'))
    H = R._load_handoff_module()
    H.validate(ledger, contract, contract_path.resolve())
    R.verify_ledger_recovery(ledger, contract)
    manifest = _bundle_manifest(bundle)
    ledger_sha = sha256_file(ledger_path)
    if str(manifest.get('originalLedgerSha256')) != ledger_sha:
        raise RotationError('recovery bundle does not bind the exact current operational ledger')
    if str(manifest.get('releaseId')) != str(ledger.get('releaseId')) or str(config.get('releaseId')) != str(ledger.get('releaseId')):
        raise RotationError('rotation config/bundle releaseId differs from the current ledger')
    bundle_sha = sha256_file(bundle)
    generation_id = f'g-{ledger_sha[:12]}-{bundle_sha[:12]}'
    state = load_state(state_path.resolve(), config, ledger, key, allow_missing=True)
    existing = next((x for x in state['generations'] if x.get('ledgerSha256') == ledger_sha), None)
    if existing is not None:
        if existing.get('bundleSha256') != bundle_sha:
            raise RotationError('this ledger already has a different sealed recovery bundle generation; reuse/verify the existing generation rather than silently replacing it')
        verify_state(state_path=state_path, config_path=config_path, ledger_path=ledger_path, key_env=key_env)
        return {'passed': True, 'idempotent': True, 'generationId': existing['generationId'], 'activeGenerationId': state.get('activeGenerationId'), 'copyCount': len(existing.get('copies') or []), 'restoreProbe': existing.get('restoreProbe')}
    receipts = []
    for destination in config['destinations']:
        receipt = _copy_to_destination(bundle, destination, generation_id, manifest, ledger_sha, key)
        receipts.append({'storageId': destination['storageId'], 'receiptHmacSha256': receipt['receiptHmacSha256'], 'bundleSha256': receipt['bundleSha256']})
    policy = config['policy']
    if len(receipts) < int(policy['minimumCopiesPerGeneration']):
        raise RotationError('new generation does not have the required minimum verified copies')
    offsite_copies = [x for x in config['destinations'] if x.get('role') == 'offsite' and x.get('offsiteDeclared') is True]
    probe_destination = offsite_copies[0] if offsite_copies else config['destinations'][0]
    probe_bundle = _generation_dir(probe_destination, str(ledger['releaseId']), generation_id) / 'recovery.zip'
    probe = _restore_probe(probe_bundle, restore_checkout.resolve(), generation_id)
    if probe.get('passed') is not True:
        raise RotationError('new generation restore probe did not pass')
    generation = {
        'generationId': generation_id,
        'releaseId': ledger['releaseId'],
        'ledgerSha256': ledger_sha,
        'bundleSha256': bundle_sha,
        'bundleSizeBytes': bundle.stat().st_size,
        'bundleManifestSha256': manifest['manifestSha256'],
        'currentSourceHeadSha': ledger['currentSourceHeadSha'],
        'lastCompletedStage': manifest.get('lastCompletedStage'),
        'nextStage': manifest.get('nextStage'),
        'createdAt': now_iso(),
        'copies': receipts,
        'restoreProbe': {**probe, 'storageId': probe_destination['storageId']},
        'status': 'active',
    }
    for old in state['generations']:
        if old.get('status') == 'active':
            old['status'] = 'retained'
    state['generations'].append(generation)
    state['activeGenerationId'] = generation_id
    state = _state_sign_write(state_path.resolve(), state, key)
    _propagate_state(state, config)
    verified = verify_state(state_path=state_path, config_path=config_path, ledger_path=ledger_path, key_env=key_env)
    return {'passed': True, 'idempotent': False, 'generationId': generation_id, 'activeGenerationId': state['activeGenerationId'], 'copyCount': len(receipts), 'generationCount': len(state['generations']), 'restoreProbe': probe, 'stateHmacSha256': state['stateHmacSha256'], 'verified': verified['passed']}


def verify_state(*, state_path: Path, config_path: Path, ledger_path: Path | None, key_env: str) -> dict[str, Any]:
    config = load_config(config_path.resolve())
    key = _key_from_env(key_env)
    if ledger_path is not None:
        ledger = json.loads(ledger_path.resolve().read_text(encoding='utf-8'))
    else:
        raw = json.loads(state_path.resolve().read_text(encoding='utf-8'))
        ledger = {'releaseId': raw.get('releaseId'), 'releaseClass': raw.get('releaseClass'), 'repository': raw.get('repository'), 'repositoryId': raw.get('repositoryId')}
    state = load_state(state_path.resolve(), config, ledger, key)
    destinations = {x['storageId']: x for x in config['destinations']}
    active = None
    verified_copies = 0
    for generation in state['generations']:
        if generation.get('releaseId') != state['releaseId']:
            raise RotationError('rotation generation releaseId differs from state')
        copies = generation.get('copies')
        if not isinstance(copies, list) or len(copies) < int(config['policy']['minimumCopiesPerGeneration']):
            raise RotationError(f'rotation generation {generation.get("generationId")} has too few copies')
        seen: set[str] = set()
        for copy in copies:
            storage_id = str(copy.get('storageId', ''))
            if storage_id in seen or storage_id not in destinations:
                raise RotationError('rotation generation has duplicate/unknown storage copy')
            seen.add(storage_id)
            receipt_path = _generation_dir(destinations[storage_id], state['releaseId'], generation['generationId']) / 'COPY_RECEIPT.json'
            if not receipt_path.is_file() or receipt_path.is_symlink():
                raise RotationError(f'copy receipt missing for {storage_id}/{generation["generationId"]}')
            receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
            _verify_receipt(receipt, destinations[storage_id], generation, key)
            if receipt.get('receiptHmacSha256') != copy.get('receiptHmacSha256'):
                raise RotationError('rotation state receipt HMAC differs from destination receipt')
            verified_copies += 1
        if generation.get('generationId') == state.get('activeGenerationId'):
            active = generation
    if not state['generations'] or active is None:
        raise RotationError('rotation state has no active generation')
    if active.get('status') != 'active' or (active.get('restoreProbe') or {}).get('passed') is not True:
        raise RotationError('active rotation generation has no passed real restore probe')
    if ledger_path is not None:
        current_ledger_sha = sha256_file(ledger_path.resolve())
        if active.get('ledgerSha256') != current_ledger_sha:
            raise RotationError('active rotation generation does not cover the exact current operational ledger; rotate the new ledger before continuing')
    return {'passed': True, 'activeGenerationId': active['generationId'], 'generationCount': len(state['generations']), 'verifiedCopyCount': verified_copies, 'currentLedgerCovered': ledger_path is None or active.get('ledgerSha256') == sha256_file(ledger_path.resolve()), 'restoreProbePassed': True, 'minimumRetainedGenerations': int(config['policy']['minimumRetainedGenerations'])}


def prune(*, state_path: Path, config_path: Path, ledger_path: Path, key_env: str, apply: bool) -> dict[str, Any]:
    verified = verify_state(state_path=state_path, config_path=config_path, ledger_path=ledger_path, key_env=key_env)
    config = load_config(config_path.resolve())
    key = _key_from_env(key_env)
    ledger = json.loads(ledger_path.resolve().read_text(encoding='utf-8'))
    state = load_state(state_path.resolve(), config, ledger, key)
    keep = int(config['policy']['minimumRetainedGenerations'])
    if len(state['generations']) <= keep:
        return {'passed': True, 'applied': False, 'prunableGenerationIds': [], 'keptGenerationIds': [x['generationId'] for x in state['generations']], 'verification': verified}
    prunable = state['generations'][:-keep]
    kept = state['generations'][-keep:]
    if not apply:
        return {'passed': True, 'applied': False, 'prunableGenerationIds': [x['generationId'] for x in prunable], 'keptGenerationIds': [x['generationId'] for x in kept], 'verification': verified}
    destinations = {x['storageId']: x for x in config['destinations']}
    for generation in prunable:
        for copy in generation.get('copies') or []:
            destination = destinations.get(copy['storageId'])
            if destination is None:
                raise RotationError('cannot safely prune copy from a destination no longer present in sealed config')
            target = _generation_dir(destination, state['releaseId'], generation['generationId'])
            receipt_path = target / 'COPY_RECEIPT.json'
            if not receipt_path.is_file():
                raise RotationError('cannot safely prune generation without its signed copy receipt')
            _verify_receipt(json.loads(receipt_path.read_text(encoding='utf-8')), destination, generation, key)
        # All copies were authenticated before deleting any of them.
        for copy in generation.get('copies') or []:
            destination = destinations[copy['storageId']]
            target = _generation_dir(destination, state['releaseId'], generation['generationId'])
            shutil.rmtree(target)
        state['retiredGenerations'].append({
            'generationId': generation['generationId'],
            'ledgerSha256': generation['ledgerSha256'],
            'bundleSha256': generation['bundleSha256'],
            'retiredAt': now_iso(),
            'reason': f'pruned only after a newer active generation passed restore verification and {keep} complete generations remain retained',
        })
    state['generations'] = kept
    state = _state_sign_write(state_path.resolve(), state, key)
    _propagate_state(state, config)
    verify_state(state_path=state_path, config_path=config_path, ledger_path=ledger_path, key_env=key_env)
    return {'passed': True, 'applied': True, 'prunedGenerationIds': [x['generationId'] for x in prunable], 'keptGenerationIds': [x['generationId'] for x in kept], 'stateHmacSha256': state['stateHmacSha256']}


def init_config(*, release_id: str, output: Path) -> dict[str, Any]:
    value = {
        'schemaVersion': 1,
        'revision': ROTATION_REVISION,
        'releaseId': release_id,
        'policy': {
            'minimumCopiesPerGeneration': 2,
            'minimumRetainedGenerations': 2,
            'requireOffsiteDeclaredCopy': True,
            'requireRestoreProbeBeforeActivation': True,
        },
        'destinations': [],
        'notice': 'Operational backup topology only. offsiteDeclared is operator/infrastructure metadata; the tool validates identity/path separation and exact bytes but cannot prove physical geography.',
    }
    value = seal_config(value)
    _atomic_json(output.resolve(), value)
    return value


def set_destination(*, config_path: Path, storage_id: str, role: str, root: Path, offsite_declared: bool) -> dict[str, Any]:
    path = config_path.resolve()
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('configSha256') != _hash_without(value, 'configSha256'):
        raise RotationError('cannot update a rotation config whose existing seal is invalid')
    destinations = [x for x in value.get('destinations') or [] if str(x.get('storageId')) != storage_id]
    destinations.append({'storageId': storage_id, 'role': role, 'root': str(root.expanduser().resolve()), 'offsiteDeclared': bool(offsite_declared)})
    value['destinations'] = destinations
    value = seal_config(value)
    # Permit intermediate one-destination config while the operator is building it; rotate/verify validate full policy.
    _atomic_json(path, value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description='Rotate, authenticate, restore-probe and safely prune independent first-real-run recovery bundle copies.')
    parser.add_argument('--key-env', default=DEFAULT_KEY_ENV)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('init-config')
    p.add_argument('--release-id', required=True)
    p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('set-destination')
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--storage-id', required=True)
    p.add_argument('--role', choices=['primary', 'offsite'], required=True)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--offsite-declared', action='store_true')
    p = sub.add_parser('rotate')
    p.add_argument('--ledger', type=Path, required=True)
    p.add_argument('--contract', type=Path, default=DEFAULT_CONTRACT)
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--state', type=Path, required=True)
    p.add_argument('--restore-checkout', type=Path, required=True)
    p = sub.add_parser('verify')
    p.add_argument('--state', type=Path, required=True)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--ledger', type=Path)
    p = sub.add_parser('prune')
    p.add_argument('--state', type=Path, required=True)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--ledger', type=Path, required=True)
    p.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'init-config':
            result = init_config(release_id=args.release_id, output=args.output)
        elif args.command == 'set-destination':
            result = set_destination(config_path=args.config, storage_id=args.storage_id, role=args.role, root=args.root, offsite_declared=args.offsite_declared)
        elif args.command == 'rotate':
            result = rotate(ledger_path=args.ledger, contract_path=args.contract, bundle=args.bundle, config_path=args.config, state_path=args.state, restore_checkout=args.restore_checkout, key_env=args.key_env)
        elif args.command == 'verify':
            result = verify_state(state_path=args.state, config_path=args.config, ledger_path=args.ledger, key_env=args.key_env)
        else:
            result = prune(state_path=args.state, config_path=args.config, ledger_path=args.ledger, key_env=args.key_env, apply=args.apply)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (RotationError, R.RecoveryError) as exc:
        print(json.dumps({'passed': False, 'error': str(exc)}, indent=2))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
