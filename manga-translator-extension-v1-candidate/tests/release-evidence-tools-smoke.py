from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATERIALIZE = ROOT / 'scripts' / 'materialize_release_profile_privacy.py'
MERGE = ROOT / 'scripts' / 'merge_release_smoke_evidence.py'
PROMOTE = ROOT / 'scripts' / 'promote_release_smoke_evidence.py'
SOURCE_SHA = 'b' * 40
TARGETS = ('linux-x86_64', 'macos-arm64', 'windows-x86_64')


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def digest_json(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_observation_digest(path: Path) -> str:
    value = json.loads(path.read_text(encoding='utf-8'))
    body = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('utf-8')
    return hashlib.sha256(body).hexdigest()


def manifest(path: Path) -> dict:
    value = {
        'schemaVersion': 2,
        'releaseId': 'v1-fixture',
        'sourceHeadSha': SOURCE_SHA,
        'qualifiedSourceHeadSha': SOURCE_SHA,
        'releaseClass': 'private-v1',
        'protocolMajor': 1,
        'exactArtifactsOnly': True,
        'rebuildDuringPromotion': False,
        'extension': {'artifact': 'extension.zip', 'sha256': '1' * 64},
        'engines': [
            {'target': 'linux-x86_64', 'artifact': 'engine-linux.tar.gz', 'sha256': '2' * 64},
            {'target': 'macos-arm64', 'artifact': 'engine-macos.tar.gz', 'sha256': '3' * 64},
            {'target': 'windows-x86_64', 'artifact': 'engine-windows.zip', 'sha256': '4' * 64},
        ],
        'metadata': [],
    }
    write_json(path, value)
    return value


def engine_observation(path: Path, manifest_sha: str, target: str, index: int, *, privacy: dict | None = None) -> None:
    artifact = {
        'linux-x86_64': ('engine-linux.tar.gz', '2' * 64),
        'macos-arm64': ('engine-macos.tar.gz', '3' * 64),
        'windows-x86_64': ('engine-windows.zip', '4' * 64),
    }[target]
    write_json(path, {
        'schemaVersion': 2,
        'id': f'engine-{target}',
        'artifactManifestSha256': manifest_sha,
        'sourceHeadSha': SOURCE_SHA,
        'kind': 'engine-artifact',
        'platform': target,
        'artifact': artifact[0],
        'artifactSha256': artifact[1],
        'testedAtUtc': '2026-08-20T00:00:00Z',
        'cleanEnvironment': True,
        'checks': {'install': True, 'activate': True, 'translateFixture': True, 'restore': True},
        'profileId': 'default-v1',
        'profileStateAtTest': 'ready',
        'profileFingerprint': 'sha256:' + str(index) * 64,
        'privacyDescriptor': privacy or {'imageLeavesDevice': False, 'ocrTextLeavesDevice': True, 'visualContextLeavesDevice': False},
        'externalProviderNames': ['OpenAI'],
        'fixtureSha256': 'a' * 64,
        'resultSha256': 'b' * 64,
        'engineVersion': '0.5.0',
        'installationMode': 'portable-clean-extract',
        'cleanInstallVerified': True,
        'installationCleanupVerified': True,
    })


def browser_observation(path: Path, manifest_sha: str, major: int) -> None:
    write_json(path, {
        'schemaVersion': 2,
        'id': f'browser-{major}',
        'artifactManifestSha256': manifest_sha,
        'sourceHeadSha': SOURCE_SHA,
        'kind': 'unpacked-extension',
        'platform': 'browser',
        'artifact': 'extension.zip',
        'artifactSha256': '1' * 64,
        'engineTargetAtTest': 'linux-x86_64',
        'engineArtifactAtTest': 'engine-linux.tar.gz',
        'engineArtifactSha256AtTest': '2' * 64,
        'browserVersion': f'{major}.0.0.1',
        'fixtureUrl': 'http://127.0.0.1:4173/fixture.html',
        'evidenceMode': 'interactive-human-observed-exact-bytes',
        'testedAtUtc': '2026-08-20T00:00:00Z',
        'cleanEnvironment': True,
        'checks': {'install': True, 'activate': True, 'translateFixture': True, 'restore': True},
    })


def orchestration_browser_session(path: Path, manifest_sha: str, engine_paths: list[Path], browser_paths: list[Path]) -> None:
    value = {
        'schemaVersion': 1,
        'revision': 'rev19-v1-evidence-orchestration-v2-public-store-closure',
        'releaseId': 'v1-fixture',
        'releaseClass': 'private-v1',
        'stage': 'browser-smoke-complete',
        'sequence': 4,
        'assemblySourceHeadSha': SOURCE_SHA,
        'qualifiedSourceHeadSha': SOURCE_SHA,
        'qualification': {
            'freezeSha256': 'c' * 64, 'freezeIdentitySha256': 'd' * 64, 'runPlanSha256': 'e' * 64,
            'packageLockSha256': 'f' * 64, 'uvLockSha256': '0' * 64,
        },
        'controlled': {
            'manifestSha256': manifest_sha, 'controlledRunId': 100,
            'candidateRunIds': {'extension': 101, 'linux': 102, 'macos': 103, 'windows': 104},
        },
        'nativeSmoke': {
            'engineSmokeRunId': 200,
            'observations': {target: canonical_observation_digest(p) for target, p in zip(TARGETS, engine_paths)},
        },
        'browserSmoke': {
            'observationsByMajor': {str(int(json.loads(p.read_text())['browserVersion'].split('.')[0])): canonical_observation_digest(p) for p in browser_paths},
        },
        'previousSessionSha256': 'a' * 64,
    }
    body = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('utf-8')
    value['sessionSha256'] = hashlib.sha256(body).hexdigest()
    write_json(path, value)


def run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(script), *args], cwd=ROOT, text=True, capture_output=True)


def main() -> int:
    checks = 0
    with tempfile.TemporaryDirectory(prefix='mte-release-evidence-') as td:
        root = Path(td)
        manifest_path = root / 'controlled-release.json'
        manifest(manifest_path)
        manifest_sha = digest_json(manifest_path)
        engine_paths = []
        for index, target in enumerate(TARGETS, start=5):
            path = root / f'{target}.json'
            engine_observation(path, manifest_sha, target, index)
            engine_paths.append(path)

        privacy_path = root / 'profile-privacy.json'
        args = ['--controlled-manifest', str(manifest_path), '--output', str(privacy_path)]
        for path in engine_paths:
            args += ['--engine-observation', str(path)]
        result = run(MATERIALIZE, *args)
        assert result.returncode == 0, result.stderr
        privacy = json.loads(privacy_path.read_text())
        assert privacy['schemaVersion'] == 2 and set(privacy['profileFingerprintsByTarget']) == set(TARGETS)
        assert len(set(privacy['profileFingerprintsByTarget'].values())) == 3
        checks += 1

        bad = root / 'bad-privacy.json'
        engine_observation(bad, manifest_sha, 'windows-x86_64', 9, privacy={'imageLeavesDevice': True, 'ocrTextLeavesDevice': True, 'visualContextLeavesDevice': False})
        bad_args = ['--controlled-manifest', str(manifest_path), '--output', str(root / 'bad-output.json')]
        for path in engine_paths[:2] + [bad]:
            bad_args += ['--engine-observation', str(path)]
        result = run(MATERIALIZE, *bad_args)
        assert result.returncode != 0 and 'privacy descriptor differs' in (result.stderr + result.stdout)
        checks += 1

        browser148 = root / 'browser148.json'; browser_observation(browser148, manifest_sha, 148)
        browser151 = root / 'browser151.json'; browser_observation(browser151, manifest_sha, 151)
        state_path = root / 'release-state.json'
        write_json(state_path, {
            'schemaVersion': 1,
            'releaseClass': 'developer-preview',
            'audit': {'chromeBaselineMajor': 148, 'currentStableMajorAtAudit': 151},
            'artifacts': {'controlledManifest': None, 'extensionSha256': None, 'engineTargets': []},
            'smoke': {'freshUnpackedChrome148Passed': False, 'freshUnpackedCurrentStablePassed': False, 'freshEngineArtifactPassedTargets': [], 'storeInstalledVersionPassed': False},
            'v1Blockers': {'phase7NativeSupportReady': False, 'chrome148RealBrowserGate': False, 'currentStableRealBrowserGate': False},
        })
        records_path = root / 'smoke-records.json'
        merge_args = ['--controlled-manifest', str(manifest_path), '--records', str(records_path), '--release-state', str(state_path), '--profile-privacy', str(privacy_path)]
        for path in engine_paths + [browser148, browser151]:
            merge_args += ['--observation', str(path)]
        result = run(MERGE, *merge_args)
        assert result.returncode == 0, result.stderr
        records = json.loads(records_path.read_text())
        state = json.loads(state_path.read_text())
        assert records['schemaVersion'] == 2 and len(records['records']) == 5
        assert state['smoke']['freshUnpackedChrome148Passed'] is True and state['smoke']['freshUnpackedCurrentStablePassed'] is True
        assert set(state['smoke']['freshEngineArtifactPassedTargets']) == set(TARGETS)
        checks += 1

        tampered = root / 'tampered-browser.json'
        browser_observation(tampered, manifest_sha, 148)
        value = json.loads(tampered.read_text()); value['artifactSha256'] = 'f' * 64; write_json(tampered, value)
        bad_merge = merge_args.copy()
        i = bad_merge.index(str(browser148)); bad_merge[i] = str(tampered)
        result = run(MERGE, *bad_merge)
        assert result.returncode != 0 and 'artifact hash differs' in (result.stderr + result.stdout)
        checks += 1

        # Transactional promotion writes all three mirrors only after the complete exact-byte set validates.
        promoted_privacy = root / 'promoted-profile-privacy.json'
        promoted_records = root / 'promoted-smoke-records.json'
        promoted_state = root / 'promoted-release-state.json'
        write_json(promoted_privacy, {'schemaVersion': 2, 'sentinel': 'old'})
        write_json(promoted_records, {'schemaVersion': 2, 'records': [], 'sentinel': 'old'})
        write_json(promoted_state, json.loads(state_path.read_text()))
        orchestration_session = root / 'browser-smoke-session.json'
        orchestration_browser_session(orchestration_session, manifest_sha, engine_paths, [browser148, browser151])
        orchestration_output = root / 'promoted-orchestration.json'
        promote_args = [
            '--controlled-manifest', str(manifest_path),
            '--profile-privacy', str(promoted_privacy),
            '--records', str(promoted_records),
            '--release-state', str(promoted_state),
            '--orchestration-session', str(orchestration_session),
            '--orchestration-output', str(orchestration_output),
        ]
        for path in engine_paths:
            promote_args += ['--engine-observation', str(path)]
        for path in (browser148, browser151):
            promote_args += ['--browser-observation', str(path)]
        result = run(PROMOTE, *promote_args)
        assert result.returncode == 0, result.stderr
        assert json.loads(promoted_privacy.read_text()).get('materializedFromControlledManifestSha256') == manifest_sha
        assert len(json.loads(promoted_records.read_text()).get('records', [])) == 5
        assert json.loads(orchestration_output.read_text()).get('stage') == 'evidence-promoted'
        checks += 1

        # A failed promotion is atomic: pre-existing evidence mirrors remain byte-identical.
        before = (promoted_privacy.read_bytes(), promoted_records.read_bytes(), promoted_state.read_bytes(), orchestration_output.read_bytes())
        bad_promote = promote_args.copy()
        index = bad_promote.index(str(browser148)); bad_promote[index] = str(tampered)
        result = run(PROMOTE, *bad_promote)
        assert result.returncode != 0
        after = (promoted_privacy.read_bytes(), promoted_records.read_bytes(), promoted_state.read_bytes(), orchestration_output.read_bytes())
        assert after == before
        checks += 1

    print(f'Release evidence tooling smoke: {checks}/6 passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
