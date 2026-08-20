from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from release_evidence import sha256_file, validate_smoke_observation
from v1_evidence_orchestrator import (
    OrchestrationError,
    next_session,
    read_session,
    read_store_handoff,
    seal_session,
    write_session,
    write_store_handoff,
)

SOURCE='a'*40
QUALIFIED='b'*40


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2)+'\n')


def manifest(path: Path, ext_sha: str) -> tuple[dict,str]:
    value={
        'schemaVersion':2,'releaseId':'v1-public-fixture','sourceHeadSha':SOURCE,'qualifiedSourceHeadSha':QUALIFIED,
        'releaseClass':'public-v1','protocolMajor':1,'exactArtifactsOnly':True,'rebuildDuringPromotion':False,
        'extension':{'artifact':'extension.zip','sha256':ext_sha,'manifestVersion':'1.0.0'},
        'engines':[
            {'target':'linux-x86_64','artifact':'linux.tar.gz','sha256':'1'*64},
            {'target':'macos-arm64','artifact':'macos.pkg','sha256':'2'*64},
            {'target':'windows-x86_64','artifact':'windows.zip','sha256':'3'*64},
        ],'metadata':[]}
    write_json(path,value)
    return value, hashlib.sha256(path.read_bytes()).hexdigest()


def evidence_promoted_public() -> dict:
    value={
        'schemaVersion':1,'revision':'rev19-v1-evidence-orchestration-v2-public-store-closure','releaseId':'v1-public-fixture',
        'releaseClass':'public-v1','stage':'evidence-promoted','sequence':5,'assemblySourceHeadSha':SOURCE,'qualifiedSourceHeadSha':QUALIFIED,
        'qualification':{'freezeSha256':'4'*64,'freezeIdentitySha256':'5'*64,'runPlanSha256':'6'*64,'packageLockSha256':'7'*64,'uvLockSha256':'8'*64},
        'controlled':{'manifestSha256':'9'*64,'controlledRunId':100,'candidateRunIds':{'extension':101,'linux':102,'macos':103,'windows':104}},
        'nativeSmoke':{'engineSmokeRunId':200,'observations':{'linux-x86_64':'a'*64,'macos-arm64':'b'*64,'windows-x86_64':'c'*64}},
        'browserSmoke':{'observationsByMajor':{'148':'d'*64,'151':'e'*64}},
        'evidencePromotion':{'profilePrivacySha256':'f'*64,'smokeRecordsSha256':'0'*64,'releaseStateSha256':'1'*64},
        'previousSessionSha256':'2'*64,
    }
    return seal_session(value)


def main() -> int:
    checks=0
    with tempfile.TemporaryDirectory(prefix='mte-public-evidence-') as raw:
        d=Path(raw)
        # Public session cannot jump directly to release-ready; it must seal post-Store evidence first.
        session=evidence_promoted_public()
        try:
            next_session(session,'release-ready','finalGate',{'passed':True})
            raise AssertionError('public session incorrectly skipped post-Store evidence stage')
        except OrchestrationError:
            pass
        payload={
            'profilePrivacySha256':'3'*64,'smokeRecordsSha256':'4'*64,'releaseStateSha256':'5'*64,'publicationStateSha256':'6'*64,
            'supportChannelsSha256':'7'*64,'productionDownloadsSha256':'8'*64,'storeCandidateMetadataSha256':'9'*64,
            'storeSubmissionHandoffSha256':'a'*64,'storeInstalledObservationsByMajor':{'148':'b'*64,'151':'c'*64},
        }
        public=next_session(session,'public-evidence-promoted','publicEvidencePromotion',payload)
        pub_path=d/'public.json'; write_session(pub_path,public)
        assert read_session(pub_path,'public-evidence-promoted')['publicEvidencePromotion']['storeInstalledObservationsByMajor']['148']=='b'*64
        checks+=1

        # Store handoff is independently content-addressed and tamper evident.
        handoff_path=d/'handoff.json'
        handoff={
            'schemaVersion':1,'revision':'rev19-store-submission-handoff-v1','releaseId':'v1-public-fixture','releaseClass':'public-v1',
            'assemblySourceHeadSha':SOURCE,'qualifiedSourceHeadSha':QUALIFIED,'orchestrationSessionSha256':session['sessionSha256'],
            'controlledManifestSha256':'d'*64,'extensionArtifact':'extension.zip','extensionSha256':'e'*64,
            'gate':'fixture','gatePassed':True,
        }
        write_store_handoff(handoff_path,handoff)
        read_store_handoff(handoff_path)
        tampered=json.loads(handoff_path.read_text()); tampered['releaseId']='other'; write_json(d/'tampered.json',tampered)
        try:
            read_store_handoff(d/'tampered.json'); raise AssertionError('tampered handoff passed')
        except OrchestrationError:
            pass
        checks+=1

        # Store-installed observation schema binds candidate + handoff + orchestration identities.
        mf=d/'controlled-release.json'; m,msha=manifest(mf,'e'*64)
        obs={
            'schemaVersion':2,'id':'store-148','artifactManifestSha256':msha,'sourceHeadSha':SOURCE,'kind':'store-installed-extension','platform':'browser',
            'artifact':'extension.zip','artifactSha256':'e'*64,'engineTargetAtTest':'linux-x86_64','engineArtifactAtTest':'linux.tar.gz',
            'engineArtifactSha256AtTest':'1'*64,'browserVersion':'148.0.0.1','testedAtUtc':'2026-08-20T00:00:00Z','cleanEnvironment':True,
            'checks':{'install':True,'activate':True,'translateFixture':True,'restore':True},'evidenceMode':'interactive-human-observed-store-installed-controlled-candidate',
            'orchestrationSessionSha256':'a'*64,'storeSubmissionHandoffSha256':'b'*64,'storeCandidateSha256':'e'*64,
            'storeItemId':'a'*32,'storeVersion':'1.0.0',
        }
        validate_smoke_observation(obs,manifest=m,manifest_sha256=msha)
        bad=dict(obs); bad.pop('storeSubmissionHandoffSha256')
        try:
            validate_smoke_observation(bad,manifest=m,manifest_sha256=msha); raise AssertionError('unbound Store observation passed')
        except ValueError:
            pass
        checks+=1

        # Exact Store candidate promotion can be cryptographically bound to the controlled archive + handoff.
        zip_path=d/'extension.zip'
        ext_manifest={'manifest_version':3,'version':'1.0.0','minimum_chrome_version':'148','permissions':['activeTab','scripting','storage','sidePanel','alarms'],'optional_host_permissions':['https://*/*','http://127.0.0.1/*'],'message_serialization':'structured_clone'}
        with zipfile.ZipFile(zip_path,'w') as z: z.writestr('manifest.json',json.dumps(ext_manifest))
        ext_sha=sha256_file(zip_path)
        m,msha=manifest(mf,ext_sha)
        handoff.update({'controlledManifestSha256':msha,'extensionSha256':ext_sha})
        write_store_handoff(handoff_path,handoff)
        out=d/'store'
        proc=subprocess.run([sys.executable,str(ROOT/'scripts/prepare_store_candidate.py'),'--zip',str(zip_path),'--tested-sha256',ext_sha,'--controlled-manifest',str(mf),'--store-submission-handoff',str(handoff_path),'--out',str(out)],cwd=ROOT,text=True,capture_output=True)
        assert proc.returncode==0,proc.stderr+proc.stdout
        candidate=json.loads((out/'candidate.json').read_text())
        assert candidate['schemaVersion']==2 and candidate['byteIdenticalToControlledExtension'] is True and candidate['controlledManifestSha256']==msha
        checks+=1

    print(f'Public release evidence tooling smoke: {checks}/4 passed')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
