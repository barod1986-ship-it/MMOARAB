from __future__ import annotations
import importlib.util, io, json, tempfile, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TOOL=ROOT/'scripts'/'first_real_run_recovery.py'
CONTRACT=ROOT/'release-control'/'production-execution-contract.json'

def load():
    spec=importlib.util.spec_from_file_location('recovery_fixture',TOOL); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def zip_bytes(name='file.txt',data=b'hello'):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z: z.writestr(name,data)
    return b.getvalue()

def ledger():
    return {'releaseId':'v1.0.0-rc1','releaseClass':'private-v1','repository':'owner/repo','repositoryId':'123','currentSourceHeadSha':'a'*40,'authorizedOperatorIds':['1'],'records':[]}

def main():
    m=load(); raw=zip_bytes(); digest='sha256:'+m.sha256_bytes(raw)
    def fake_get(url,token,version):
        if '/actions/runs/' in url and '/artifacts' not in url:
            rid=url.rstrip('/').rsplit('/',1)[-1]
            return {'id':int(rid),'name':'wf','path':'.github/workflows/x.yml','display_title':'readiness intent=mte-test-recovery','event':'workflow_dispatch','status':'completed','conclusion':'success','head_branch':'main','head_sha':'a'*40,'actor':{'id':1,'login':'op'}}
        if '/artifacts' in url:
            return {'artifacts':[{'id':77,'name':'critical','size_in_bytes':5,'expired':False,'created_at':'2026-08-20T00:00:00Z','expires_at':'2026-09-20T00:00:00Z','digest':digest}]}
        raise AssertionError(url)
    m.api_get_json=fake_get; m.download_artifact_archive=lambda ledger,aid,token,version: raw
    with tempfile.TemporaryDirectory(prefix='mte-recovery-test-') as td0:
        td=Path(td0); ld=ledger(); obs=[{'runId':'101','workflow':'.github/workflows/x.yml'}]
        # 1. Capture stores exact artifact bytes and verifies GitHub digest.
        s=m.capture_automated_stage(ledger=ld,stage='qualification-execute',observations=obs,token='t',version='2026-03-10',root=td,minimum_artifacts=1)
        manifest=m.verify_summary(s,stage='qualification-execute',expected_run_ids=['101'],source_head_sha='a'*40)
        assert manifest['artifactCount']==1 and manifest['runSummaries'][0]['artifactCount']==1
        # 2. Capture is idempotent and does not redownload if snapshot already exists.
        m.download_artifact_archive=lambda *a,**k: (_ for _ in ()).throw(AssertionError('redownloaded'))
        s2=m.capture_automated_stage(ledger=ld,stage='qualification-execute',observations=obs,token='t',version='2026-03-10',root=td,minimum_artifacts=1)
        assert s2['manifestSha256']==s['manifestSha256']
        # 3. Byte tampering is detected offline.
        stage_dir=m.snapshot_path_from_summary(s); art=next((stage_dir/'runs'/'101'/'artifacts').glob('*.zip')); original=art.read_bytes(); art.write_bytes(original+b'x')
        try: m.verify_summary(s,stage='qualification-execute'); raise AssertionError('tamper accepted')
        except m.RecoveryError as exc: assert 'mismatch' in str(exc)
        art.write_bytes(original); m.verify_summary(s,stage='qualification-execute')
        # 4. Expired artifact fails closed before a ledger record could be committed.
        def expired_get(url,token,version):
            if '/artifacts' in url: return {'artifacts':[{'id':78,'name':'expired','size_in_bytes':1,'expired':True,'digest':None}]}
            return fake_get(url,token,version)
        m.api_get_json=expired_get
        try: m.capture_automated_stage(ledger=ld,stage='controlled-assembly',observations=obs,token='t',version='v',root=td,minimum_artifacts=1); raise AssertionError('expired accepted')
        except m.RecoveryError as exc: assert 'expired' in str(exc)
        # 5. GitHub digest mismatch fails closed.
        def mismatch_get(url,token,version):
            if '/artifacts' in url: return {'artifacts':[{'id':79,'name':'bad','size_in_bytes':1,'expired':False,'digest':'sha256:'+'0'*64}]}
            return fake_get(url,token,version)
        m.api_get_json=mismatch_get; m.download_artifact_archive=lambda *a,**k: raw
        try: m.capture_automated_stage(ledger=ld,stage='native-engine-smoke',observations=obs,token='t',version='v',root=td,minimum_artifacts=1); raise AssertionError('digest mismatch accepted')
        except m.RecoveryError as exc: assert 'digest differs' in str(exc)
        # 6. Manual checkpoint evidence bytes are archived and tamper-detectable.
        cp=td/'checkpoint-source.json'; ev=td/'evidence-source.json'; cp.write_text('{"ok":true}\n'); ev.write_text('{"evidence":1}\n')
        ms=m.capture_manual_stage(ledger=ld,stage='benchmark-review',checkpoint_path=cp,evidence={'run-plan':ev},root=td)
        mm=m.verify_summary(ms,stage='benchmark-review',expected_run_ids=[],source_head_sha='a'*40); assert mm['kind']=='manual-stage'
        # 7. Export now requires a structurally valid production ledger/recovery chain and verifies offline.
        contract=json.loads(CONTRACT.read_text())
        h=m._load_handoff_module()
        prod={
            'schemaVersion':4,'revision':h.LEDGER_REVISION,'releaseId':'v1.0.0-rc1','releaseClass':'private-v1',
            'repository':'owner/repo','repositoryId':'123','defaultBranch':'main','initialSourceHeadSha':'a'*40,'currentSourceHeadSha':'a'*40,
            'workflowSetSha256':m._workflow_set_sha256(ROOT,contract),'onboardingConfigSha256':'f'*64,
            'authorizedOperatorIds':['1'],'authorizedOperatorLogins':['op'],'contractSha256':m.sha256_file(CONTRACT),
            'createdAt':'2026-08-20T00:00:00Z','records':[],
        }
        prod=h.seal(prod)
        m.api_get_json=fake_get; m.download_artifact_archive=lambda *a,**k: raw
        robs=[{'runId':'101','workflow':'.github/workflows/x.yml','displayTitle':'readiness intent=mte-test-recovery'}]
        rs=m.capture_automated_stage(ledger=prod,stage='github-infrastructure-audit',observations=robs,token='t',version='v',root=td,minimum_artifacts=1)
        h.append_record(prod,'github-infrastructure-audit',runIntentNonce='mte-test-recovery',runObservations=robs,recoverySnapshot=rs)
        h.append_record(prod,'live-runner-readiness',runIntentNonce='mte-test-recovery',runObservations=robs,reusedControllerRunFrom='github-infrastructure-audit',recoverySnapshotRef={'stage':'github-infrastructure-audit','manifestSha256':rs['manifestSha256']})
        prod=h.seal(prod)
        ledger_path=td/'ledger.json'; ledger_path.write_text(json.dumps(prod,indent=2,sort_keys=True)+'\n')
        bundle=td/'recovery.zip'; out=m.export_bundle(ledger_path=ledger_path,contract_path=CONTRACT,output=bundle); assert out['snapshotCount']==1
        verified=m.verify_bundle(bundle); assert verified['passed'] and verified['snapshotCount']==1 and verified['nextStage']=='qualification-prepare'
    print('First real run recovery tooling: 7/7 passed')
    return 0

if __name__=='__main__': raise SystemExit(main())
