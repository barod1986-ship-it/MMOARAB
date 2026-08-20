from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from v1_evidence_orchestrator import next_session, read_session, write_session
ORCH = ROOT / 'scripts' / 'v1_evidence_orchestrator.py'
SOURCE = 'a' * 40
QUALIFIED = 'b' * 40
FREEZE_FILE_SHA = 'f' * 64
TARGETS = ('linux-x86_64', 'macos-arm64', 'windows-x86_64')


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seal_session(path: Path, stage='qualification-promoted') -> None:
    value = {
        'schemaVersion': 1,
        'revision': 'rev19-v1-evidence-orchestration-v2-public-store-closure',
        'releaseId': 'v1-rc-fixture',
        'releaseClass': 'private-v1',
        'stage': stage,
        'sequence': 1,
        'assemblySourceHeadSha': SOURCE,
        'qualifiedSourceHeadSha': QUALIFIED,
        'qualification': {
            'freezeSha256': FREEZE_FILE_SHA,
            'freezeIdentitySha256': '1' * 64,
            'runPlanSha256': '2' * 64,
            'packageLockSha256': '3' * 64,
            'uvLockSha256': '4' * 64,
        },
        'previousSessionSha256': None,
    }
    body = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()
    value['sessionSha256'] = hashlib.sha256(body).hexdigest()
    write_json(path, value)


def manifest(path: Path, *, qualified=QUALIFIED) -> str:
    value = {
        'schemaVersion': 2,
        'releaseId': 'v1-rc-fixture',
        'sourceHeadSha': SOURCE,
        'qualifiedSourceHeadSha': qualified,
        'releaseClass': 'private-v1',
        'protocolMajor': 1,
        'exactArtifactsOnly': True,
        'rebuildDuringPromotion': False,
        'extension': {'artifact': 'extension.zip', 'sha256': '5' * 64},
        'engines': [
            {'target': 'linux-x86_64', 'artifact': 'engine-linux.tar.gz', 'sha256': '6' * 64},
            {'target': 'macos-arm64', 'artifact': 'engine-macos.tar.gz', 'sha256': '7' * 64},
            {'target': 'windows-x86_64', 'artifact': 'engine-windows.zip', 'sha256': '8' * 64},
        ],
        'metadata': [{'artifact': 'production-profile-freeze.json', 'sha256': FREEZE_FILE_SHA}],
    }
    write_json(path, value)
    return digest(path)


def engine_obs(path: Path, manifest_sha: str, target: str, index: int) -> None:
    artifact, sha = {
        'linux-x86_64': ('engine-linux.tar.gz', '6' * 64),
        'macos-arm64': ('engine-macos.tar.gz', '7' * 64),
        'windows-x86_64': ('engine-windows.zip', '8' * 64),
    }[target]
    write_json(path, {
        'schemaVersion': 2, 'id': f'engine-{target}', 'artifactManifestSha256': manifest_sha,
        'sourceHeadSha': SOURCE, 'kind': 'engine-artifact', 'platform': target,
        'artifact': artifact, 'artifactSha256': sha, 'testedAtUtc': '2026-08-20T00:00:00Z',
        'cleanEnvironment': True, 'checks': {'install': True, 'activate': True, 'translateFixture': True, 'restore': True},
        'profileId': 'default-v1', 'profileStateAtTest': 'ready', 'profileFingerprint': 'sha256:' + str(index) * 64,
        'privacyDescriptor': {'imageLeavesDevice': False, 'ocrTextLeavesDevice': True, 'visualContextLeavesDevice': False},
        'externalProviderNames': ['OpenAI'], 'fixtureSha256': '9' * 64, 'resultSha256': 'a' * 64,
        'engineVersion': '0.5.0', 'installationMode': 'portable-clean-extract', 'cleanInstallVerified': True,
        'installationCleanupVerified': True,
    })


def browser_obs(path: Path, manifest_sha: str, major: int, orchestration_sha: str) -> None:
    write_json(path, {
        'schemaVersion': 2, 'id': f'browser-{major}', 'artifactManifestSha256': manifest_sha,
        'sourceHeadSha': SOURCE, 'orchestrationSessionSha256': orchestration_sha, 'kind': 'unpacked-extension', 'platform': 'browser',
        'artifact': 'extension.zip', 'artifactSha256': '5' * 64,
        'engineTargetAtTest': 'linux-x86_64', 'engineArtifactAtTest': 'engine-linux.tar.gz',
        'engineArtifactSha256AtTest': '6' * 64, 'browserVersion': f'{major}.0.0.1',
        'fixtureUrl': 'http://127.0.0.1:4173/fixture.html', 'evidenceMode': 'interactive-human-observed-exact-bytes',
        'testedAtUtc': '2026-08-20T00:00:00Z', 'cleanEnvironment': True,
        'checks': {'install': True, 'activate': True, 'translateFixture': True, 'restore': True},
    })


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(ORCH), *args], cwd=ROOT, text=True, capture_output=True)


def main() -> int:
    checks = 0
    with tempfile.TemporaryDirectory(prefix='mte-orchestration-') as td:
        d = Path(td)
        s1 = d/'s1.json'; seal_session(s1)
        mf = d/'controlled-release.json'; msha = manifest(mf)
        s2 = d/'s2.json'
        r = run('controlled', '--session', str(s1), '--controlled-manifest', str(mf), '--controlled-run-id','100', '--extension-run-id','101','--linux-run-id','102','--macos-run-id','103','--windows-run-id','104','--output',str(s2))
        assert r.returncode == 0, r.stderr
        assert json.loads(s2.read_text())['stage'] == 'controlled-assembled'
        checks += 1

        # Wrong qualified identity is rejected even when assembly commit and artifact bytes look valid.
        badmf=d/'bad-controlled.json'; manifest(badmf, qualified='c'*40)
        r=run('controlled','--session',str(s1),'--controlled-manifest',str(badmf),'--controlled-run-id','100','--extension-run-id','101','--linux-run-id','102','--macos-run-id','103','--windows-run-id','104','--output',str(d/'bad.json'))
        assert r.returncode != 0 and 'qualified source commit differs' in r.stderr
        checks += 1

        engines=[]
        for i,t in enumerate(TARGETS, 1):
            p=d/f'{t}.json'; engine_obs(p,msha,t,i); engines.append(p)
        s3=d/'s3.json'
        args=['native','--session',str(s2),'--controlled-manifest',str(mf),'--engine-smoke-run-id','200','--output',str(s3)]
        for p in engines: args += ['--engine-observation',str(p)]
        r=run(*args); assert r.returncode==0,r.stderr
        assert json.loads(s3.read_text())['stage']=='native-smoke-complete'
        checks += 1

        # Skipping native stage is impossible.
        r=run('browser','--session',str(s2),'--controlled-manifest',str(mf),'--release-state',str(d/'missing.json'),'--output',str(d/'skip.json'))
        assert r.returncode != 0 and 'stage ordering violation' in r.stderr
        checks += 1

        state=d/'release-state.json'; write_json(state, {'audit': {'chromeBaselineMajor':148,'currentStableMajorAtAudit':151}})
        native_session_sha=json.loads(s3.read_text())['sessionSha256']
        b148=d/'b148.json'; b151=d/'b151.json'; browser_obs(b148,msha,148,native_session_sha); browser_obs(b151,msha,151,native_session_sha)
        s4=d/'s4.json'
        r=run('browser','--session',str(s3),'--controlled-manifest',str(mf),'--release-state',str(state),'--browser-observation',str(b148),'--browser-observation',str(b151),'--output',str(s4))
        assert r.returncode==0,r.stderr
        assert json.loads(s4.read_text())['stage']=='browser-smoke-complete'
        checks += 1

        privacy=d/'privacy.json'; write_json(privacy, {'materializedFromControlledManifestSha256':msha})
        record_items=[json.loads(p.read_text()) for p in [*engines,b148,b151]]
        records=d/'records.json'; write_json(records, {'controlledManifestSha256':msha,'sourceHeadSha':SOURCE,'records':record_items})
        promoted_state=d/'promoted-state.json'; write_json(promoted_state, {'releaseClass':'private-v1','artifacts':{'controlledManifest':'release/controlled/v1-rc-fixture/controlled-release.json'}})
        s5=d/'s5.json'
        r=run('promoted','--session',str(s4),'--controlled-manifest',str(mf),'--profile-privacy',str(privacy),'--smoke-records',str(records),'--release-state',str(promoted_state),'--output',str(s5))
        assert r.returncode==0,r.stderr
        assert json.loads(s5.read_text())['stage']=='evidence-promoted'
        checks += 1

        # Private V1 may advance directly from evidence-promoted to release-ready;
        # public-only post-Store validation must not reject the later private stage.
        s6=d/'s6-private-ready.json'
        private_ready=next_session(read_session(s5,'evidence-promoted'),'release-ready','finalGate',{'gate':'fixture','targetClass':'private-v1','passed':True})
        write_session(s6,private_ready)
        assert read_session(s6,'release-ready')['releaseClass']=='private-v1'
        checks += 1

        # Tampering any prior session field without resealing is detected.
        tampered=d/'tampered.json'; value=json.loads(s4.read_text()); value['releaseId']='other'; write_json(tampered,value)
        r=run('verify','--session',str(tampered)); assert r.returncode != 0 and 'hash does not verify' in r.stderr
        checks += 1

    print(f'V1 orchestration tooling smoke: {checks}/8 passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
