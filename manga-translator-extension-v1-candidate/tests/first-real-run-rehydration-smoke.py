from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / 'scripts' / 'first_real_run_recovery.py'
CONTRACT_REL = Path('release-control/production-execution-contract.json')


def load():
    spec = importlib.util.spec_from_file_location('rehydration_fixture', RECOVERY)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def run_git(root: Path, *args: str, env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(['git', *args], cwd=root, text=True, capture_output=True, env=env)
    if proc.returncode != 0:
        raise AssertionError(f'git {" ".join(args)} failed: {proc.stderr}')
    return proc.stdout.strip()


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


def init_repo(path: Path) -> str:
    run_git(path, 'init', '-b', 'main')
    run_git(path, 'config', 'user.email', 'recovery-test@example.invalid')
    run_git(path, 'config', 'user.name', 'Recovery Test')
    run_git(path, 'add', '.')
    env = dict(os.environ)
    env['GIT_AUTHOR_DATE'] = '2026-08-20T12:00:00Z'
    env['GIT_COMMITTER_DATE'] = '2026-08-20T12:00:00Z'
    run_git(path, 'commit', '-m', 'recovery fixture source', env=env)
    run_git(path, 'remote', 'add', 'origin', 'https://github.com/owner/repo.git')
    return run_git(path, 'rev-parse', 'HEAD').lower()


def main() -> int:
    m = load()
    with tempfile.TemporaryDirectory(prefix='mte-rehydrate-smoke-') as td0:
        td = Path(td0)
        source = td / 'source'
        target = td / 'target'
        copy_source_tree(source)
        head = init_repo(source)
        contract_path = source / CONTRACT_REL
        contract = json.loads(contract_path.read_text(encoding='utf-8'))
        h = m._load_handoff_module()
        ledger = {
            'schemaVersion': 4,
            'revision': h.LEDGER_REVISION,
            'releaseId': 'v1.0.0-rehydrate-test',
            'releaseClass': 'private-v1',
            'repository': 'owner/repo',
            'repositoryId': '123456',
            'defaultBranch': 'main',
            'initialSourceHeadSha': head,
            'currentSourceHeadSha': head,
            'workflowSetSha256': m._workflow_set_sha256(source, contract),
            'onboardingConfigSha256': 'f' * 64,
            'authorizedOperatorIds': ['42'],
            'authorizedOperatorLogins': ['operator'],
            'contractSha256': m.sha256_file(contract_path),
            'createdAt': '2026-08-20T12:00:00Z',
            'records': [],
            'notice': 'test production-shaped operational ledger',
        }
        ledger = h.seal(ledger)
        artifact_raw = __import__('io').BytesIO()
        import zipfile
        with zipfile.ZipFile(artifact_raw, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('readiness.json', b'{"passed":true}\n')
        artifact_bytes = artifact_raw.getvalue()
        artifact_digest = 'sha256:' + m.sha256_bytes(artifact_bytes)

        def fake_get(url: str, token: str, version: str):
            if '/actions/runs/' in url and '/artifacts' not in url:
                return {
                    'id': 101,
                    'name': 'production-readiness',
                    'path': '.github/workflows/production-execution-readiness.yml',
                    'display_title': 'readiness intent=mte-rehydrate-1234567890',
                    'event': 'workflow_dispatch',
                    'status': 'completed',
                    'conclusion': 'success',
                    'head_branch': 'main',
                    'head_sha': head,
                    'run_number': 1,
                    'run_attempt': 1,
                    'created_at': '2026-08-20T12:01:00Z',
                    'updated_at': '2026-08-20T12:02:00Z',
                    'html_url': 'https://github.com/owner/repo/actions/runs/101',
                    'actor': {'id': 42, 'login': 'operator'},
                }
            if '/artifacts' in url:
                return {'artifacts': [{
                    'id': 501,
                    'name': 'production-execution-readiness',
                    'size_in_bytes': len(artifact_bytes),
                    'expired': False,
                    'created_at': '2026-08-20T12:02:00Z',
                    'expires_at': '2026-09-20T12:02:00Z',
                    'digest': artifact_digest,
                }]}
            raise AssertionError(url)

        m.api_get_json = fake_get
        m.download_artifact_archive = lambda *a, **k: artifact_bytes
        observations = [{
            'runId': '101',
            'workflow': '.github/workflows/production-execution-readiness.yml',
            'displayTitle': 'readiness intent=mte-rehydrate-1234567890',
        }]
        snap = m.capture_automated_stage(
            ledger=ledger,
            stage='github-infrastructure-audit',
            observations=observations,
            token='unused',
            version='2026-03-10',
            root=source / 'release' / 'recovery',
            minimum_artifacts=1,
        )
        h.append_record(ledger, 'github-infrastructure-audit', runIntentNonce='mte-rehydrate-1234567890', runObservations=observations, recoverySnapshot=snap)
        h.append_record(ledger, 'live-runner-readiness', runIntentNonce='mte-rehydrate-1234567890', runObservations=observations, reusedControllerRunFrom='github-infrastructure-audit', recoverySnapshotRef={'stage': 'github-infrastructure-audit', 'manifestSha256': snap['manifestSha256']})
        ledger = h.seal(ledger)
        ledger_path = source / 'release' / 'first-real-run-ledger.json'
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        bundle = td / 'recovery.zip'

        # 1. Production-shaped export is self-validating and source/workflow bound.
        exported = m.export_bundle(ledger_path=ledger_path, contract_path=contract_path, output=bundle)
        assert exported['snapshotCount'] == 1 and exported['nextStage'] == 'qualification-prepare'
        assert m.verify_bundle(bundle)['passed']

        # Fresh checkout has no release/recovery operational state from the source workspace.
        proc = subprocess.run(['git', 'clone', '--quiet', str(source), str(target)], text=True, capture_output=True)
        assert proc.returncode == 0, proc.stderr
        run_git(target, 'remote', 'set-url', 'origin', 'https://github.com/owner/repo.git')
        assert not (target / 'release' / 'recovery').exists()

        # 2. Restore is atomic under release/rehydrated and rewrites only recovery paths in a resealed ledger.
        restored = m.restore_bundle(bundle=bundle, checkout=target)
        assert restored['passed'] and restored['nextStage'] == 'qualification-prepare' and not restored['idempotent']
        restore_root = Path(restored['restoreRoot'])
        restored_ledger = Path(restored['ledger'])
        assert restore_root.is_dir() and restored_ledger.is_file()
        assert (restore_root / 'artifact-catalog.json').is_file()

        # 3. Repeating restore of the exact bundle is idempotent, not destructive.
        again = m.restore_bundle(bundle=bundle, checkout=target)
        assert again['passed'] and again['idempotent'] and Path(again['restoreRoot']) == restore_root

        # 4. Bundle can disappear after activation; restored state verifies fully offline.
        bundle.unlink()
        verified = m.verify_restored(checkout=target, restore_root=restore_root)
        assert verified['passed'] and verified['nextStage'] == 'qualification-prepare'

        # 5. The actual controller can plan/resume from the new checkout without GitHub artifact storage.
        controller = target / 'scripts' / 'first_real_run_controller.py'
        cp = subprocess.run([sys.executable, str(controller), 'plan', '--ledger', str(restored_ledger)], cwd=target, text=True, capture_output=True)
        assert cp.returncode == 0, cp.stdout + cp.stderr
        plan = json.loads(cp.stdout)
        assert plan['passed'] and plan['nextStage'] == 'qualification-prepare'

        # 6. Restored artifact-byte tampering is detected without contacting GitHub.
        artifact = next((restore_root / 'recovery').rglob('*.zip'))
        original = artifact.read_bytes()
        artifact.write_bytes(original + b'tamper')
        try:
            m.verify_restored(checkout=target, restore_root=restore_root)
            raise AssertionError('tampered restored artifact accepted')
        except m.RecoveryError as exc:
            assert 'mismatch' in str(exc)
        artifact.write_bytes(original)
        assert m.verify_restored(checkout=target, restore_root=restore_root)['passed']

        # 7. Repository-origin substitution is rejected before restoration/continuation.
        run_git(target, 'remote', 'set-url', 'origin', 'https://github.com/attacker/other.git')
        try:
            m.verify_restored(checkout=target, restore_root=restore_root)
            raise AssertionError('wrong origin accepted')
        except m.RecoveryError as exc:
            assert 'identity/cursor' in str(exc)
        run_git(target, 'remote', 'set-url', 'origin', 'https://github.com/owner/repo.git')

        # 8. Source HEAD drift after restore is rejected even when recovery bytes remain intact.
        run_git(target, 'config', 'user.email', 'recovery-test@example.invalid')
        run_git(target, 'config', 'user.name', 'Recovery Test')
        (target / 'DRIFT.txt').write_text('drift\n', encoding='utf-8')
        run_git(target, 'add', 'DRIFT.txt')
        run_git(target, 'commit', '-m', 'drift')
        try:
            m.verify_restored(checkout=target, restore_root=restore_root)
            raise AssertionError('drifted checkout accepted')
        except m.RecoveryError as exc:
            assert 'integrity' in str(exc).lower() or 'identity/cursor' in str(exc).lower()

    print('First real run rehydration tooling: 8/8 passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
