from __future__ import annotations
import importlib.util, json, subprocess, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CONTROLLER=ROOT/'scripts'/'first_real_run_controller.py'
HANDOFF=ROOT/'scripts'/'first_real_run_handoff.py'
PROVISION=ROOT/'scripts'/'provision_github_production_infrastructure.py'
CONTRACT=ROOT/'release-control'/'production-execution-contract.json'
MANUAL=ROOT/'scripts'/'manual_boundary_checkpoint.py'


def load(path:Path,name:str):
    spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def make_onboarding(path:Path):
    m=load(PROVISION,'prov_ctrl_fixture'); c=m.load_contract(CONTRACT)
    cfg=m.render_template(c,CONTRACT,'owner/repo')
    for i,role in enumerate(c['selfHostedRoles'],1): cfg=m.set_runner_name(cfg,c,role['role'],f'runner-{i}')
    cfg=m.set_operator(cfg,'release-operator')
    cfg['repositoryBinding']={'repositoryId':123,'fullName':'owner/repo','defaultBranch':'main','defaultBranchHeadSha':'a'*40,
      'workflowSetSha256':m.workflow_set_sha256(c),'sourceIntegritySha256':m.file_sha256(ROOT/'SOURCE_SHA256SUMS.txt'),
      'authorizedOperators':[{'login':'release-operator','id':'12345'}]}
    cfg=m.seal_config(cfg); m.validate_config(cfg,c,CONTRACT,require_binding=True,check_local_binding=False)
    path.write_text(json.dumps(cfg,indent=2)+'\n'); return cfg


def init_ledger(path:Path,onboarding:Path,release_class='private-v1'):
    r=subprocess.run([sys.executable,str(HANDOFF),'init','--output',str(path),'--release-id','v1.0.0-rc1','--release-class',release_class,'--onboarding-config',str(onboarding)],cwd=ROOT,text=True,capture_output=True)
    assert r.returncode==0, r.stdout+r.stderr


def main():
    c=json.loads(CONTRACT.read_text())
    with tempfile.TemporaryDirectory(prefix='mte-controller-') as td0:
        td=Path(td0); onboarding=td/'onboarding.json'; make_onboarding(onboarding); ledger_path=td/'ledger.json'; init_ledger(ledger_path,onboarding)
        ctl=load(CONTROLLER,'controller_fixture')
        h=ctl.H
        ctl.D.verify_ledger_recovery=lambda ledger,contract: {'passed':True}
        ctl.capture_recovery=lambda stage,ledger,observations,contract,token,version: {'revision':'rev33-first-real-run-recovery-v2','stage':stage,'relativePath':f'release/recovery/test/{stage}','manifestSha256':('1' if stage!='qualification-prepare' else '2')*64,'runIds':[str(x['runId']) for x in observations],'artifactCount':1,'capturedAt':'2026-08-20T00:00:00Z'}
        manual=load(MANUAL,'manual_controller_fixture')
        def append_manual(data,stage):
            cp={'schemaVersion':1,'revision':manual.CHECKPOINT_REVISION,'stage':stage,'releaseId':data['releaseId'],'releaseClass':data['releaseClass'],'repository':data['repository'],'repositoryId':data['repositoryId'],'sourceHeadSha':data['currentSourceHeadSha'],'operator':{'id':'12345','login':'release-operator'},'reviewedAtUtc':'2026-08-20T00:00:00Z','evidence':[{'role':'fixture-evidence','fileName':'fixture.json','sha256':'e'*64,'sizeBytes':1}],'semanticBinding':{'kind':'fixture'},'notice':'fixture'}
            cp['checkpointSha256']=manual.digest_body(cp)
            h.append_record(data,stage,manualReviewed=True,manualCheckpoint=cp,recoverySnapshot={'revision':'rev33-first-real-run-recovery-v2','stage':stage,'relativePath':f'release/recovery/test/{stage}','manifestSha256':'3'*64,'runIds':[],'artifactCount':0,'capturedAt':'2026-08-20T00:00:00Z'})
        run_db={}; next_id=[100]
        dispatch_calls=[]
        def fake_head(ledger,token,version): return None
        def fake_dispatch(ledger,workflow,inputs,token,version):
            next_id[0]+=1; rid=str(next_id[0]); dispatch_calls.append((workflow,dict(inputs),rid))
            title=f'{Path(workflow).stem}'; mode=inputs.get('mode'); title=(f'Production qualification / {mode}' if mode else title); run_db[rid]={'id':int(rid),'status':'completed','conclusion':'success','event':'workflow_dispatch','head_sha':ledger['currentSourceHeadSha'],'head_branch':ledger['defaultBranch'],'path':workflow,'display_title':f'{title} / intent={inputs["run_intent_nonce"]}','actor':{'login':'release-operator','id':'12345'}}
            return rid
        def fake_get_run(ledger,rid,token,version): return dict(run_db[str(rid)])
        def fake_h_api(url,token,version): return fake_get_run(json.loads(ledger_path.read_text()),url.rsplit('/',1)[-1],token,version)
        ctl.assert_live_default_branch_head=fake_head; ctl.dispatch_workflow=fake_dispatch; ctl.get_run=fake_get_run; h.api_get=fake_h_api
        h.verify_created_pr_stage=lambda stage,nonce,ledger,contract,token,snapshot: {'prNumber':1,'url':'https://github.com/owner/repo/pull/1','headRef':f'qualification-evidence/run-250-{nonce}','headSha':'d'*40,'baseRef':'main','baseSha':ledger['currentSourceHeadSha'],'allowlist':'qualification-evidence','changedPaths':contract['firstRealRun']['sourceTransitionAllowlists']['qualification-evidence']['paths']}
        ctl.recover_run_by_nonce=lambda *a,**k: None
        ctl.wait_for_run=lambda ledger,rid,token,version,poll,timeout: fake_get_run(ledger,rid,token,version)

        # 1. One readiness dispatch records both audit and live-runner readiness via the explicit reuse contract.
        r=ctl.advance(ledger_path,c,CONTRACT,'token',{},0.01,1)
        assert r['recordedStages']==['github-infrastructure-audit','live-runner-readiness'] and len(dispatch_calls)==1
        data=json.loads(ledger_path.read_text()); assert len(data['records'])==2 and data['records'][0]['runIntentNonce']==data['records'][1]['runIntentNonce'] and 'pendingLaunch' not in data

        # 2. Required qualification inputs are rejected before a pending launch or dispatch exists.
        try: ctl.advance(ledger_path,c,CONTRACT,'token',{},0.01,1); raise AssertionError('missing qualification inputs accepted')
        except ctl.ControllerError as exc: assert 'requires controller input' in str(exc)
        assert 'pendingLaunch' not in json.loads(ledger_path.read_text()) and len(dispatch_calls)==1

        # 3. Qualification prepare dispatch is nonce-bound and recorded only after verified success.
        r=ctl.advance(ledger_path,c,CONTRACT,'token',{'input_bundle_relative':'bundle.json','workspace_relative':'ws'},0.01,1)
        assert r['recordedStages']==['qualification-prepare'] and dispatch_calls[-1][1]['mode']=='prepare' and dispatch_calls[-1][1]['run_intent_nonce'].startswith('mte-')
        data=json.loads(ledger_path.read_text()); assert data['records'][-1]['runObservations'][0]['displayTitle'].find(data['records'][-1]['runIntentNonce'])>=0

        # Move across manual benchmark review with the handoff helper, then test recovery of a response-lost execute dispatch.
        append_manual(data,'benchmark-review'); h.write(ledger_path,data); data=json.loads(ledger_path.read_text()); h.validate(data,c,CONTRACT)
        pending=ctl.create_pending('qualification-execute',data,c,{'corpus_relative':'corpus.json','benchmark_review_relative':'review.json'})
        assert pending['dispatches'][0]['inputs']['workspace_relative']=='ws'  # inherited from the successful prepare record, never retyped
        nonce=pending['runIntentNonce']; recovered_id='250'
        run_db[recovered_id]={'id':250,'status':'completed','conclusion':'success','event':'workflow_dispatch','head_sha':'a'*40,'head_branch':'main','path':'.github/workflows/qualify-production-ml-self-hosted.yml','display_title':f'Production qualification / execute / intent={nonce}','actor':{'login':'release-operator','id':'12345'}}
        data['pendingLaunch']=pending; h.write(ledger_path,data)
        before=len(dispatch_calls)
        ctl.recover_run_by_nonce=lambda ledger,workflow,n,token,version: recovered_id if n==nonce else None
        r=ctl.advance(ledger_path,c,CONTRACT,'token',{},0.01,1)
        assert r['recordedStages']==['qualification-execute'] and len(dispatch_calls)==before and r['runIds']==[recovered_id]

        # 4. A failed run remains pending and cannot be silently converted to success.
        # Advance qualification PR creation; inject a failed dispatch.
        ctl.recover_run_by_nonce=lambda *a,**k: None
        old_dispatch=ctl.dispatch_workflow
        def fail_dispatch(ledger,workflow,inputs,token,version):
            rid=old_dispatch(ledger,workflow,inputs,token,version); run_db[rid]['conclusion']='failure'; return rid
        ctl.dispatch_workflow=fail_dispatch
        try: ctl.advance(ledger_path,c,CONTRACT,'token',{},0.01,1); raise AssertionError('failed run recorded')
        except ctl.ControllerError as exc: assert 'conclusion' in str(exc)
        failed=json.loads(ledger_path.read_text()); assert failed.get('pendingLaunch',{}).get('stage')=='qualification-evidence-pr-created'

        # 5. retry-failed archives the failed intent and launches a fresh nonce rather than mutating the old launch.
        ctl.dispatch_workflow=old_dispatch
        r=ctl.retry_failed(ledger_path,c,CONTRACT,'token',0.01,1)
        retried=json.loads(ledger_path.read_text()); assert r['recordedStages']==['qualification-evidence-pr-created'] and retried.get('failedLaunches') and retried['failedLaunches'][0]['runIntentNonce']!=retried['records'][-1]['runIntentNonce']

        # 6. Public exact-artifact workflow-set resolves public signing input consistently on all three Engine builds.
        public_path=td/'public.json'; init_ledger(public_path,onboarding,'public-v1'); pub=json.loads(public_path.read_text())
        # Fabricate validated prior stage records only to exercise input resolver in isolation.
        nonce0='mte-public-fixture-0001'
        for stage in c['firstRealRun']['stagePlans']['public-v1'][:7]:
            if stage in c['firstRealRun']['sourceCommitTransitionStages']:
                pub['currentSourceHeadSha']='b'*40
                h.append_record(pub,stage,sourceHeadShaBefore='a'*40,sourceHeadShaAfter='b'*40,pullRequest={'prNumber':1})
                pub['records'][-1]['sourceHeadShaBefore']='a'*40
            elif (c['firstRealRun']['stageLaunchHints'].get(stage) or {}).get('kind') in {'workflow','workflow-set'}:
                wf=(c['firstRealRun']['stageLaunchHints'][stage].get('workflow') or '.github/workflows/x.yml')
                h.append_record(pub,stage,runIntentNonce=nonce0,runObservations=[{'runId':'1','workflow':wf,'displayTitle':nonce0}],recoverySnapshot={'revision':'rev33-first-real-run-recovery-v2','stage':stage,'relativePath':f'release/recovery/test/{stage}','manifestSha256':'4'*64,'runIds':['1'],'artifactCount':0,'capturedAt':'2026-08-20T00:00:00Z'})
            else:
                if stage in c['firstRealRun']['manualReviewBoundaries']: append_manual(pub,stage)
                else: h.append_record(pub,stage,manualReviewed=False)
        specs=ctl.resolve_dispatches('exact-artifact-builds',pub,c,{},'mte-public-resolve-0001')
        engine=[x for x in specs if 'release-engine-' in x['workflow']]
        assert len(specs)==4 and all(x['inputs']['public_release'] is True for x in engine) and all(x['inputs']['run_intent_nonce']=='mte-public-resolve-0001' for x in specs)

    print('First real run controller tooling: 7/7 passed')
    return 0

if __name__=='__main__': raise SystemExit(main())
