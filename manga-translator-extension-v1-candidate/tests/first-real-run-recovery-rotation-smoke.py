from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROTATION = ROOT / 'scripts' / 'first_real_run_recovery_rotation.py'
CONTRACT_REL = Path('release-control/production-execution-contract.json')


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def git(root: Path, *args: str, env=None) -> str:
    p = subprocess.run(['git', *args], cwd=root, text=True, capture_output=True, env=env)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def copy_source_tree(dst: Path) -> None:
    dst.mkdir(parents=True)
    manifest = ROOT / 'SOURCE_SHA256SUMS.txt'
    shutil.copyfile(manifest, dst / 'SOURCE_SHA256SUMS.txt')
    for line in manifest.read_text(encoding='utf-8').splitlines():
        if not line:
            continue
        _, rel = line.split('  ', 1)
        src = ROOT / rel
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)


def fixture(td: Path):
    rot = load(ROTATION, 'rotation_fixture')
    rec = rot.R
    source = td / 'source'
    copy_source_tree(source)
    git(source, 'init', '-b', 'main')
    git(source, 'config', 'user.email', 'rotation-test@example.invalid')
    git(source, 'config', 'user.name', 'Rotation Test')
    git(source, 'add', '.')
    env = dict(os.environ)
    env['GIT_AUTHOR_DATE'] = '2026-08-20T12:00:00Z'
    env['GIT_COMMITTER_DATE'] = '2026-08-20T12:00:00Z'
    git(source, 'commit', '-m', 'rotation fixture', env=env)
    git(source, 'remote', 'add', 'origin', 'https://github.com/owner/repo.git')
    head = git(source, 'rev-parse', 'HEAD').lower()
    contract_path = source / CONTRACT_REL
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    h = rec._load_handoff_module()
    ledger = {
        'schemaVersion': 4,
        'revision': h.LEDGER_REVISION,
        'releaseId': 'v1.0.0-rotation-test',
        'releaseClass': 'private-v1',
        'repository': 'owner/repo',
        'repositoryId': '123456',
        'defaultBranch': 'main',
        'initialSourceHeadSha': head,
        'currentSourceHeadSha': head,
        'workflowSetSha256': rec._workflow_set_sha256(source, contract),
        'onboardingConfigSha256': 'f' * 64,
        'authorizedOperatorIds': ['42'],
        'authorizedOperatorLogins': ['operator'],
        'contractSha256': rec.sha256_file(contract_path),
        'createdAt': '2026-08-20T12:00:00Z',
        'records': [],
        'notice': 'rotation fixture',
    }
    ledger = h.seal(ledger)
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('readiness.json', b'{"passed":true}\n')
    artifact_bytes = raw.getvalue()
    digest = 'sha256:' + rec.sha256_bytes(artifact_bytes)

    def fake_get(url: str, token: str, version: str):
        if '/actions/runs/' in url and '/artifacts' not in url:
            return {
                'id': 101, 'name': 'production-readiness',
                'path': '.github/workflows/production-execution-readiness.yml',
                'display_title': 'readiness intent=mte-rotation-1234567890',
                'event': 'workflow_dispatch', 'status': 'completed', 'conclusion': 'success',
                'head_branch': 'main', 'head_sha': head, 'run_number': 1, 'run_attempt': 1,
                'created_at': '2026-08-20T12:01:00Z', 'updated_at': '2026-08-20T12:02:00Z',
                'html_url': 'https://github.com/owner/repo/actions/runs/101',
                'actor': {'id': 42, 'login': 'operator'},
            }
        if '/artifacts' in url:
            return {'artifacts': [{
                'id': 501, 'name': 'production-execution-readiness', 'size_in_bytes': len(artifact_bytes),
                'expired': False, 'created_at': '2026-08-20T12:02:00Z', 'expires_at': '2026-09-20T12:02:00Z',
                'digest': digest,
            }]}
        raise AssertionError(url)

    rec.api_get_json = fake_get
    rec.download_artifact_archive = lambda *a, **k: artifact_bytes
    obs = [{'runId': '101', 'workflow': '.github/workflows/production-execution-readiness.yml', 'displayTitle': 'readiness intent=mte-rotation-1234567890'}]
    snap = rec.capture_automated_stage(ledger=ledger, stage='github-infrastructure-audit', observations=obs, token='unused', version='2026-03-10', root=source / 'release' / 'recovery', minimum_artifacts=1)
    h.append_record(ledger, 'github-infrastructure-audit', runIntentNonce='mte-rotation-1234567890', runObservations=obs, recoverySnapshot=snap)
    h.append_record(ledger, 'live-runner-readiness', runIntentNonce='mte-rotation-1234567890', runObservations=obs, reusedControllerRunFrom='github-infrastructure-audit', recoverySnapshotRef={'stage': 'github-infrastructure-audit', 'manifestSha256': snap['manifestSha256']})
    ledger = h.seal(ledger)
    ledger_path = source / 'release' / 'first-real-run-ledger.json'
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return rot, rec, h, source, contract_path, ledger_path


def reseal_note(h, ledger_path: Path, suffix: str):
    value = json.loads(ledger_path.read_text(encoding='utf-8'))
    value['notice'] = f'rotation fixture {suffix}'
    value = h.seal(value)
    ledger_path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def main() -> int:
    os.environ['MTE_RECOVERY_ROTATION_HMAC_KEY'] = 'test-only-rotation-hmac-key-' + ('x' * 40)
    with tempfile.TemporaryDirectory(prefix='mte-rotation-smoke-') as td0:
        td = Path(td0)
        rot, rec, h, source, contract_path, ledger_path = fixture(td)
        config_path = td / 'rotation-config.json'
        state_path = td / 'rotation-state.json'
        primary = td / 'vault-primary'
        offsite = td / 'vault-offsite'
        rot.init_config(release_id='v1.0.0-rotation-test', output=config_path)
        rot.set_destination(config_path=config_path, storage_id='vault-primary', role='primary', root=primary, offsite_declared=False)
        rot.set_destination(config_path=config_path, storage_id='vault-offsite', role='offsite', root=offsite, offsite_declared=True)
        config = rot.load_config(config_path)
        assert len(config['destinations']) == 2 and config['policy']['minimumRetainedGenerations'] == 2

        # 1. First generation: two independent copies + real restore probe before activation.
        bundle1 = td / 'recovery-1.zip'
        rec.export_bundle(ledger_path=ledger_path, contract_path=contract_path, output=bundle1)
        g1 = rot.rotate(ledger_path=ledger_path, contract_path=contract_path, bundle=bundle1, config_path=config_path, state_path=state_path, restore_checkout=source, key_env='MTE_RECOVERY_ROTATION_HMAC_KEY')
        assert g1['passed'] and g1['copyCount'] == 2 and g1['restoreProbe']['passed']
        assert rot.verify_state(state_path=state_path, config_path=config_path, ledger_path=ledger_path, key_env='MTE_RECOVERY_ROTATION_HMAC_KEY')['passed']

        # 2. Idempotent retry does not create a duplicate generation.
        again = rot.rotate(ledger_path=ledger_path, contract_path=contract_path, bundle=bundle1, config_path=config_path, state_path=state_path, restore_checkout=source, key_env='MTE_RECOVERY_ROTATION_HMAC_KEY')
        assert again['idempotent'] and again['generationId'] == g1['generationId']

        # 3. Copy-byte tampering is detected independently of the source bundle.
        copy1 = primary / 'v1.0.0-rotation-test' / g1['generationId'] / 'recovery.zip'
        original = copy1.read_bytes()
        copy1.write_bytes(original + b'tamper')
        try:
            rot.verify_state(state_path=state_path, config_path=config_path, ledger_path=ledger_path, key_env='MTE_RECOVERY_ROTATION_HMAC_KEY')
            raise AssertionError('tampered backup copy accepted')
        except rot.RotationError as exc:
            assert 'bytes differ' in str(exc) or 'mismatch' in str(exc)
        copy1.write_bytes(original)

        # 4. Rotation-state tampering is rejected cryptographically.
        state_original = state_path.read_bytes()
        state = json.loads(state_path.read_text(encoding='utf-8'))
        state['notice'] = 'tampered'
        state_path.write_text(json.dumps(state), encoding='utf-8')
        try:
            rot.verify_state(state_path=state_path, config_path=config_path, ledger_path=ledger_path, key_env='MTE_RECOVERY_ROTATION_HMAC_KEY')
            raise AssertionError('tampered signed state accepted')
        except rot.RotationError as exc:
            assert 'HMAC' in str(exc)
        state_path.write_bytes(state_original)

        # 5. A changed ledger is not covered until a new generation is rotated.
        reseal_note(h, ledger_path, 'generation-2')
        try:
            rot.verify_state(state_path=state_path, config_path=config_path, ledger_path=ledger_path, key_env='MTE_RECOVERY_ROTATION_HMAC_KEY')
            raise AssertionError('stale rotation state accepted for changed ledger')
        except rot.RotationError as exc:
            assert 'exact current operational ledger' in str(exc)
        bundle2 = td / 'recovery-2.zip'
        rec.export_bundle(ledger_path=ledger_path, contract_path=contract_path, output=bundle2)
        g2 = rot.rotate(ledger_path=ledger_path, contract_path=contract_path, bundle=bundle2, config_path=config_path, state_path=state_path, restore_checkout=source, key_env='MTE_RECOVERY_ROTATION_HMAC_KEY')
        assert g2['generationId'] != g1['generationId']

        # 6. Third verified generation permits safe pruning of only the oldest generation; two remain.
        reseal_note(h, ledger_path, 'generation-3')
        bundle3 = td / 'recovery-3.zip'
        rec.export_bundle(ledger_path=ledger_path, contract_path=contract_path, output=bundle3)
        g3 = rot.rotate(ledger_path=ledger_path, contract_path=contract_path, bundle=bundle3, config_path=config_path, state_path=state_path, restore_checkout=source, key_env='MTE_RECOVERY_ROTATION_HMAC_KEY')
        dry = rot.prune(state_path=state_path, config_path=config_path, ledger_path=ledger_path, key_env='MTE_RECOVERY_ROTATION_HMAC_KEY', apply=False)
        assert dry['prunableGenerationIds'] == [g1['generationId']] and len(dry['keptGenerationIds']) == 2
        applied = rot.prune(state_path=state_path, config_path=config_path, ledger_path=ledger_path, key_env='MTE_RECOVERY_ROTATION_HMAC_KEY', apply=True)
        assert applied['prunedGenerationIds'] == [g1['generationId']]
        assert not (primary / 'v1.0.0-rotation-test' / g1['generationId']).exists()
        assert not (offsite / 'v1.0.0-rotation-test' / g1['generationId']).exists()
        assert rot.verify_state(state_path=state_path, config_path=config_path, ledger_path=ledger_path, key_env='MTE_RECOVERY_ROTATION_HMAC_KEY')['generationCount'] == 2

        # 7. Policy refuses configurations without a declared off-site copy or with overlapping roots.
        bad = rot.init_config(release_id='v1.0.0-rotation-test', output=td / 'bad.json')
        rot.set_destination(config_path=td / 'bad.json', storage_id='a', role='primary', root=td / 'a', offsite_declared=False)
        rot.set_destination(config_path=td / 'bad.json', storage_id='b', role='primary', root=td / 'b', offsite_declared=False)
        try:
            rot.load_config(td / 'bad.json')
            raise AssertionError('no-offsite topology accepted')
        except rot.RotationError as exc:
            assert 'offsite' in str(exc).lower()
        nested = td / 'nested.json'
        rot.init_config(release_id='v1.0.0-rotation-test', output=nested)
        rot.set_destination(config_path=nested, storage_id='a', role='primary', root=td / 'vault', offsite_declared=False)
        rot.set_destination(config_path=nested, storage_id='b', role='offsite', root=td / 'vault' / 'child', offsite_declared=True)
        try:
            rot.load_config(nested)
            raise AssertionError('nested backup roots accepted')
        except rot.RotationError as exc:
            assert 'overlap' in str(exc).lower() or 'nest' in str(exc).lower()

        # 8. A bundle from a different ledger cannot be substituted into a signed generation directory.
        state = json.loads(state_path.read_text(encoding='utf-8'))
        active = next(x for x in state['generations'] if x['generationId'] == g3['generationId'])
        active_copy = primary / 'v1.0.0-rotation-test' / g3['generationId'] / 'recovery.zip'
        active_original = active_copy.read_bytes()
        active_copy.write_bytes(bundle2.read_bytes())
        receipt_path = active_copy.parent / 'COPY_RECEIPT.json'
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        # Even if an attacker also rewrote unsigned size/hash fields in state, signed receipt/HMAC and embedded ledger binding reject it.
        try:
            rot.verify_state(state_path=state_path, config_path=config_path, ledger_path=ledger_path, key_env='MTE_RECOVERY_ROTATION_HMAC_KEY')
            raise AssertionError('cross-ledger recovery bundle substitution accepted')
        except rot.RotationError:
            pass
        active_copy.write_bytes(active_original)

    print('First real run recovery rotation tooling: 8/8 passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
