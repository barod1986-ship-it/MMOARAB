from __future__ import annotations
import importlib.util, json, os, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CONTROLLER=ROOT/'scripts'/'first_real_run_controller.py'
CONTRACT=ROOT/'release-control'/'production-execution-contract.json'
MANUAL=ROOT/'scripts'/'manual_boundary_checkpoint.py'


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def main():
    ctl=load(CONTROLLER,'ctl_evidence_transition'); h=ctl.H; manual=load(MANUAL,'manual_evidence_transition'); c=json.loads(CONTRACT.read_text())
    ctl.D.verify_ledger_recovery=lambda ledger,contract: {'passed':True}
    def rec(stage,run_ids=None):
        return {'revision':'rev33-first-real-run-recovery-v2','stage':stage,'relativePath':f'release/recovery/test/{stage}','manifestSha256':('a'+str(len(stage)%9))*32,'runIds':list(run_ids or []),'artifactCount':0,'capturedAt':'2026-08-20T00:00:00Z'}
    with tempfile.TemporaryDirectory(prefix='mte-evidence-controller-') as td0:
        td=Path(td0); ledger_path=td/'ledger.json'
        ledger={'schemaVersion':4,'revision':h.LEDGER_REVISION,'releaseId':'v1.0.0-rc1','releaseClass':'private-v1','repository':'owner/repo','repositoryId':123,'defaultBranch':'main','initialSourceHeadSha':'a'*40,'currentSourceHeadSha':'a'*40,'workflowSetSha256':'f'*64,'onboardingConfigSha256':'e'*64,'authorizedOperatorIds':['12345'],'authorizedOperatorLogins':['release-operator'],'contractSha256':h.file_sha256(CONTRACT),'createdAt':'2026-08-20T00:00:00Z','records':[],'notice':'fixture'}
        nonce='mte-fixture-intent-0001'
        def auto(stage,wfs):
            obs=[{'runId':str(i+1),'workflow':wf,'displayTitle':nonce} for i,wf in enumerate(wfs)]
            h.append_record(ledger,stage,runIntentNonce=nonce,runObservations=obs,recoverySnapshot=rec(stage,[x['runId'] for x in obs]))
        def man(stage):
            cp={'schemaVersion':1,'revision':manual.CHECKPOINT_REVISION,'stage':stage,'releaseId':ledger['releaseId'],'releaseClass':ledger['releaseClass'],'repository':ledger['repository'],'repositoryId':ledger['repositoryId'],'sourceHeadSha':ledger['currentSourceHeadSha'],'operator':{'id':'12345','login':'release-operator'},'reviewedAtUtc':'2026-08-20T00:00:00Z','evidence':[{'role':'fixture','fileName':'f','sha256':'e'*64,'sizeBytes':1}],'semanticBinding':{'kind':'fixture'},'notice':'fixture'}; cp['checkpointSha256']=manual.digest_body(cp); h.append_record(ledger,stage,manualReviewed=True,manualCheckpoint=cp,recoverySnapshot=rec(stage,[]))
        hints=c['firstRealRun']['stageLaunchHints']
        auto('github-infrastructure-audit',[hints['github-infrastructure-audit']['workflow']]); auto('live-runner-readiness',[hints['live-runner-readiness']['workflow']]); auto('qualification-prepare',[hints['qualification-prepare']['workflow']]); man('benchmark-review'); auto('qualification-execute',[hints['qualification-execute']['workflow']])
        h.append_record(ledger,'qualification-evidence-pr-created',runIntentNonce=nonce,runObservations=[{'runId':'6','workflow':hints['qualification-evidence-pr-created']['workflow'],'displayTitle':nonce}],pullRequestCreated={'prNumber':1,'headRef':'qualification-evidence/run-5-'+nonce,'headSha':'d'*40},recoverySnapshot=rec('qualification-evidence-pr-created',['6']))
        before=ledger['currentSourceHeadSha']; ledger['currentSourceHeadSha']='b'*40; h.append_record(ledger,'qualification-evidence-pr-merged',sourceHeadShaBefore=before,sourceHeadShaAfter='b'*40,pullRequest={'prNumber':1,'mergeCommitSha':'b'*40,'changedPaths':['package-lock.json','engine/uv.lock','engine/mte_engine/benchmark/production-profile-freeze.json','SOURCE_SHA256SUMS.txt']}); ledger['records'][-1]['sourceHeadShaBefore']=before
        h.append_record(ledger,'qualification-evidence-checkout-reconciled',checkoutReconciliation={'revision':'rev31-post-merge-checkout-reconciliation-v1','reconciledHeadSha':'b'*40,'mergeStage':'qualification-evidence-pr-merged','reviewedChangedPaths':['package-lock.json','engine/uv.lock','engine/mte_engine/benchmark/production-profile-freeze.json','SOURCE_SHA256SUMS.txt'],'sourceIntegrityManifestSha256':'9'*64})
        auto('exact-artifact-builds',hints['exact-artifact-builds']['workflows']); auto('controlled-assembly',[hints['controlled-assembly']['workflow']]); auto('native-engine-smoke',[hints['native-engine-smoke']['workflow']]); man('chrome-148-and-stable-smoke')
        h.write(ledger_path,ledger); ledger=json.loads(ledger_path.read_text()); h.validate(ledger,c,CONTRACT); assert h.next_stage(ledger,c)=='release-evidence-local-promotion'

        pending={'revision':ctl.E.REVISION,'stage':'release-evidence-local-promotion','sourceHeadSha':'b'*40,'allowlist':'release-smoke-evidence','branch':'evidence/release-evidence/v1.0.0-rc1-bbbbbbbbbbbb-1111111111111111','prIntentNonce':'mte-pr-'+'1'*32,'changedPaths':['release-control/v1-orchestration.json','SOURCE_SHA256SUMS.txt'],'files':{'release-control/v1-orchestration.json':{'sha256':'1'*64,'sizeBytes':10},'SOURCE_SHA256SUMS.txt':{'sha256':'2'*64,'sizeBytes':20}}}
        created={'prNumber':22,'url':'https://github.com/owner/repo/pull/22','headRef':pending['branch'],'headSha':'c'*40,'baseRef':'main','baseSha':'b'*40,'allowlist':'release-smoke-evidence','changedPaths':pending['changedPaths'],'files':pending['files'],'creator':{'id':'12345','login':'release-operator'},'prIntentNonce':pending['prIntentNonce']}
        ctl.assert_live_default_branch_head=lambda *a,**k:None; ctl.E.pending_snapshot=lambda *a,**k:dict(pending); ctl.E.validate_pending=lambda *a,**k:None; ctl.E.create_or_recover=lambda **k:dict(created)
        old=os.environ.get('MTE_PRODUCTION_EVIDENCE_PR_TOKEN'); os.environ['MTE_PRODUCTION_EVIDENCE_PR_TOKEN']='pr-token'
        try:
            # 1. One controller advance atomically records local promotion + exact PR-created identity.
            r=ctl.advance(ledger_path,c,CONTRACT,'controller-token',{},0.01,1); assert r['recordedStages']==['release-evidence-local-promotion','release-evidence-pr-created'] and r['pullRequest']['prNumber']==22
            data=json.loads(ledger_path.read_text()); assert data['records'][-1]['pullRequestCreated']['headSha']=='c'*40 and 'pendingEvidencePr' not in data

            # 2. Exact recorded PR remains a human boundary while unmerged; controller does not accept another PR number.
            unmerged={'pullRequest':{'number':22,'merged_at':None,'base':{'ref':'main'},'head':{'ref':created['headRef'],'sha':'c'*40}},'mergeCommit':{},'files':[]}
            h.load_pr_observation=lambda *a,**k:unmerged
            r=ctl.advance(ledger_path,c,CONTRACT,'controller-token',{},0.01,1); assert r['blocked'] and r['pullRequest']['prNumber']==22 and h.next_stage(json.loads(ledger_path.read_text()),c)=='release-evidence-pr-merged'

            # 3. After human merge, controller verifies same PR/head and exact live merge HEAD before advancing the source cursor.
            merged={'pullRequest':{'number':22,'merged_at':'2026-08-20T01:00:00Z','merge_commit_sha':'e'*40,'base':{'ref':'main'},'head':{'ref':created['headRef'],'sha':'c'*40}},'mergeCommit':{'sha':'e'*40,'parents':[{'sha':'b'*40}]},'files':[{'filename':x,'status':'modified'} for x in pending['changedPaths']]}
            h.load_pr_observation=lambda *a,**k:merged; ctl.assert_live_default_branch_is=lambda *a,**k:None
            r=ctl.advance(ledger_path,c,CONTRACT,'controller-token',{},0.01,1); assert r['advanced'] and r['currentSourceHeadSha']=='e'*40 and r['recordedStages']==['release-evidence-pr-merged']
            assert h.next_stage(json.loads(ledger_path.read_text()),c)=='release-evidence-checkout-reconciled'
            ctl.assert_live_default_branch_head=lambda *a,**k:None; ctl.R.reconcile_checkout=lambda **k:{'revision':ctl.R.REVISION,'reconciledHeadSha':'e'*40,'mergeStage':'release-evidence-pr-merged','reviewedChangedPaths':pending['changedPaths'],'sourceIntegrityManifestSha256':'8'*64}
            r=ctl.advance(ledger_path,c,CONTRACT,'controller-token',{},0.01,1); assert r['advanced'] and r['recordedStages']==['release-evidence-checkout-reconciled']
        finally:
            if old is None: os.environ.pop('MTE_PRODUCTION_EVIDENCE_PR_TOKEN',None)
            else: os.environ['MTE_PRODUCTION_EVIDENCE_PR_TOKEN']=old
    print('Evidence transition controller: 3/3 passed')
    return 0

if __name__=='__main__': raise SystemExit(main())
