from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREPARE = ROOT / 'scripts' / 'prepare_controlled_release.py'
VERIFY = ROOT / 'scripts' / 'verify_controlled_release_ready.py'
SOURCE_SHA = 'c' * 40

spec = importlib.util.spec_from_file_location('release_ready', VERIFY)
assert spec and spec.loader
release_ready = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_ready)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extension_zip(path: Path) -> None:
    manifest = {
        'manifest_version': 3,
        'name': 'fixture',
        'version': '0.9.0',
        'minimum_chrome_version': '148',
        'permissions': ['activeTab', 'scripting', 'storage', 'sidePanel', 'alarms'],
        'optional_host_permissions': ['https://*/*', 'http://127.0.0.1/*'],
        'message_serialization': 'structured_clone',
    }
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('sidepanel.html', 'ok')


def main() -> int:
    with tempfile.TemporaryDirectory(prefix='mte-ready-gate-') as td:
        root = Path(td)
        ext = root / 'extension.zip'
        engine = root / 'mte-local-engine-0.5.0-linux-x86_64.tar.gz'
        compat = root / f'{engine.name}.compatibility.json'
        extension_zip(ext)
        engine.write_bytes(b'engine-fixture')
        compat.write_text(json.dumps({
            'schemaVersion': 1,
            'target': 'linux-x86_64',
            'engineVersion': '0.5.0',
            'protocolMajor': 1,
            'artifact': engine.name,
            'sha256': 'sha256:' + digest(engine),
            'signed': False,
            'notarized': False,
        }), encoding='utf-8')
        out = root / 'release' / 'controlled'
        result = subprocess.run([
            sys.executable, str(PREPARE), '--release-id', 'fixture-rc1', '--release-class', 'developer-preview',
            '--source-head-sha', SOURCE_SHA, '--extension-zip', str(ext), '--extension-sha256', digest(ext),
            '--engine', f'{engine}::{compat}::{digest(engine)}', '--out', str(out),
        ], cwd=ROOT, text=True, capture_output=True)
        assert result.returncode == 0, result.stderr
        release_dir = out / 'fixture-rc1'
        state = {
            'releaseClass': 'developer-preview',
            'artifacts': {
                'controlledManifest': 'release/controlled/fixture-rc1/controlled-release.json',
                'extensionSha256': digest(release_dir / ext.name),
                'engineTargets': ['linux-x86_64'],
            },
        }
        blockers: list[str] = []
        manifest, manifest_path, manifest_sha = release_ready.verify_controlled_manifest(root, state, blockers)
        assert manifest is not None and manifest_path is not None and manifest_sha and not blockers, blockers

        # Regression: untracked directories/symlinks cannot hide beside immutable release files.
        junk = release_dir / 'junk'
        junk.mkdir()
        blockers = []
        release_ready.verify_controlled_manifest(root, state, blockers)
        assert any('non-regular/untracked entries' in item for item in blockers), blockers
        junk.rmdir()

        # Regression: exact ZIP permission drift is rejected even if manifest hashes are otherwise valid.
        bad_ext = root / 'bad-extension.zip'
        with zipfile.ZipFile(bad_ext, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json', json.dumps({
                'manifest_version': 3, 'name': 'fixture', 'version': '0.9.0', 'minimum_chrome_version': '148',
                'permissions': ['activeTab', 'scripting', 'storage', 'sidePanel', 'alarms', 'tabs'],
                'optional_host_permissions': ['https://*/*', 'http://127.0.0.1/*'],
                'message_serialization': 'structured_clone',
            }))
        blockers = []
        release_ready.inspect_extension_zip(bad_ext, blockers)
        assert any('required permission drift' in item for item in blockers), blockers

        # Regression: a manifest cannot claim bytes that do not exist.
        (release_dir / engine.name).unlink()
        blockers = []
        release_ready.verify_controlled_manifest(root, state, blockers)
        assert any('Engine artifact is missing' in item for item in blockers), blockers

        # Regression: zero-byte/fabricated lockfiles cannot satisfy the gate.
        (root / 'package.json').write_text(json.dumps({'name': 'x', 'version': '1.0.0', 'dependencies': {}, 'devDependencies': {}}), encoding='utf-8')
        (root / 'package-lock.json').write_bytes(b'')
        blockers = []
        release_ready.verify_package_lock(root, blockers)
        assert blockers and any('invalid JSON' in item for item in blockers), blockers

        (root / 'engine').mkdir(exist_ok=True)
        (root / 'engine' / 'pyproject.toml').write_text('[project]\nname="x"\nversion="1.0.0"\ndependencies=[]\n', encoding='utf-8')
        (root / 'engine' / 'uv.lock').write_bytes(b'')
        blockers = []
        release_ready.verify_uv_lock(root, blockers)
        assert blockers, 'empty uv.lock must not be accepted'

        # Regression: release metadata cannot claim remote-transfer consent unless executable source proves both boundaries.
        source_state = {'releaseClass': 'developer-preview', 'v1Blockers': {'remoteTextTransferConsentReady': True}}
        blockers = []
        assert release_ready.verify_remote_transfer_consent_implementation(ROOT, source_state, blockers) is True, blockers
        assert not blockers, blockers

        contract_root = root / 'tampered-source'
        contract_files = [
            'scripts/verify_remote_transfer_consent_contract.py',
            'src/ui/remote-transfer-consent.ts', 'src/engine/local-processing-gateway.ts', 'src/engine/types.ts',
            'src/messaging/background-handlers.ts', 'src/messaging/protocol.ts', 'src/entrypoints/sidepanel/main.tsx',
            'src/pipeline/coordinator.ts', 'engine/mte_engine/consent.py', 'engine/mte_engine/models.py',
            'engine/mte_engine/app.py', 'engine/mte_engine/profile.py', 'engine/tests/test_remote_transfer_consent.py',
        ]
        for rel in contract_files:
            dst = contract_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, dst)
        gateway = contract_root / 'src/engine/local-processing-gateway.ts'
        gateway.write_text(gateway.read_text(encoding='utf-8').replace('REMOTE_TRANSFER_CONSENT_REQUIRED', 'CONSENT_BYPASSED'), encoding='utf-8')
        blockers = []
        assert release_ready.verify_remote_transfer_consent_implementation(contract_root, source_state, blockers) is False
        assert any('extension create/start enforcement' in item for item in blockers), blockers

        # Regression: private/public V1 cannot bypass production role/SFX or inpainting qualification evidence.
        v1_state = {
            'releaseClass': 'private-v1',
            'v1Blockers': {
                'productionRuntimeAdaptersComplete': True,
                'productionRoleSfxClassifierReady': True,
                'productionInpainterRuntimeReady': True,
            },
        }
        good_freeze = {
            'selected': {'inpainter': 'lama-inpaint'},
            'selectedArtifacts': [{'artifactId': 'lama-big', 'kind': 'inpaint', 'sha256': 'sha256:' + 'a' * 64}],
            'roleSafetyQualification': {
                'roleClassifierRevision': 'visual-enclosure-sfx-guard-v1',
                'roleClassifierSfxProtectedRecall': 1.0,
                'sentToTranslatorRate': 0.0,
                'eraseInpaintMaskOverlapRate': 0.0,
                'changedPixelRateAfterEncodeDecode': 0.0,
                'uncertainDestructiveEditRate': 0.0,
                'protectedConflictSilentOverwriteCount': 0,
                'independentGroundTruthPages': 10,
            },
            'inpaintingQualification': {
                'candidateId': 'lama-inpaint',
                'humanScore': 4.5,
                'humanCriticalFailures': 0,
                'pagesReviewed': 20,
                'criticalReviewFailures': 0,
            },
        }
        blockers = []
        release_ready.verify_v1_ml_runtime_evidence(ROOT, v1_state, good_freeze, blockers)
        assert not blockers, blockers

        bad_freeze = json.loads(json.dumps(good_freeze))
        bad_freeze['roleSafetyQualification']['roleClassifierSfxProtectedRecall'] = 0.99
        bad_freeze['inpaintingQualification']['humanScore'] = 3.99
        blockers = []
        release_ready.verify_v1_ml_runtime_evidence(ROOT, v1_state, bad_freeze, blockers)
        assert any('role/SFX classifier qualification' in item for item in blockers), blockers
        assert any('inpainting winner qualification' in item for item in blockers), blockers

        # Regression: V1 cannot bypass the evidence ordering/session chain even if individual evidence files are supplied.
        blockers = []
        release_ready.verify_v1_orchestration(root, {'releaseClass': 'private-v1'}, manifest, manifest_sha, None, blockers)
        assert any('orchestration checkpoint is missing' in item for item in blockers), blockers

    print('Phase 9 release-ready regression smoke: 11/11 passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
