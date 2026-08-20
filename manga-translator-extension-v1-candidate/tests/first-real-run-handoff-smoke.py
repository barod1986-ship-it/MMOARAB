from __future__ import annotations
import importlib.util, json, subprocess, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TOOL=ROOT/'scripts'/'first_real_run_handoff.py'
PROVISION=ROOT/'scripts'/'provision_github_production_infrastructure.py'
CONTRACT=ROOT/'release-control'/'production-execution-contract.json'
MANUAL_SMOKE=ROOT/'tests'/'manual-boundary-checkpoint-smoke.py'
MANUAL_TOOL=ROOT/'scripts'/'manual_boundary_checkpoint.py'


def load_module(path:Path,name:str):
    spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def run(*args):
    return subprocess.run([sys.executable,str(TOOL),*args],cwd=ROOT,text=True,capture_output=True)


def make_onboarding(path:Path):
    spec=importlib.util.spec_from_file_location('mte_provision_fixture',PROVISION)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    contract=m.load_contract(CONTRACT)
    cfg=m.render_template(contract,CONTRACT,'owner/repo')
    for i,role in enumerate(contract['selfHostedRoles'],1): cfg=m.set_runner_name(cfg,contract,role['role'],f'runner-{i}')
    cfg=m.set_operator(cfg,'release-operator')
    cfg['repositoryBinding']={
      'repositoryId':123,'fullName':'owner/repo','defaultBranch':'main','defaultBranchHeadSha':'a'*40,
      'workflowSetSha256':m.workflow_set_sha256(contract),'sourceIntegritySha256':m.file_sha256(ROOT/'SOURCE_SHA256SUMS.txt'),
      'authorizedOperators':[{'login':'release-operator','id':'12345'}]
    }
    cfg=m.seal_config(cfg); m.validate_config(cfg,contract,CONTRACT,require_binding=True,check_local_binding=False)
    path.write_text(json.dumps(cfg,indent=2)+'\n')
    return cfg


def run_snapshot(path:Path, run_id:int, workflow:str, sha:str, *, title:str='production run', nonce:str='mte-test-intent-0001', actor:str='release-operator', actor_id:str='12345'):
    path.write_text(json.dumps({
      'id':run_id,'conclusion':'success','event':'workflow_dispatch','head_sha':sha,'head_branch':'main',
      'path':workflow,'display_title':f'{title} / intent={nonce}','actor':{'login':actor,'id':actor_id}
    }))


def created_pr_snapshot(path:Path, number:int, before:str, head_sha:str, branch:str, files:list[str]):
    path.write_text(json.dumps({
      'pullRequest':{'number':number,'html_url':f'https://github.com/owner/repo/pull/{number}','base':{'ref':'main'},'head':{'ref':branch,'sha':head_sha,'repo':{'full_name':'owner/repo'}}},
      'headCommit':{'sha':head_sha,'parents':[{'sha':before}]},
      'files':[{'filename':f,'status':'modified'} for f in files],
    }))


def pr_snapshot(path:Path, number:int, before:str, after:str, head_sha:str, branch:str, files:list[str]):
    path.write_text(json.dumps({
      'pullRequest':{'number':number,'merged_at':'2026-08-20T00:00:00Z','merge_commit_sha':after,'base':{'ref':'main'},'head':{'ref':branch,'sha':head_sha}},
      'mergeCommit':{'sha':after,'parents':[{'sha':before}]},
      'files':[{'filename':f,'status':'modified'} for f in files],
    }))


def main():
    contract=json.loads(CONTRACT.read_text())
    handoff=load_module(TOOL,'mte_handoff_fixture_direct')
    with tempfile.TemporaryDirectory(prefix='mte-first-run-') as td:
        td=Path(td); onboarding=td/'onboarding.json'; cfg=make_onboarding(onboarding); ledger=td/'ledger.json'; runs=td/'runs'; runs.mkdir()
        r=run('init','--output',str(ledger),'--release-id','v1.0.0-rc1','--release-class','private-v1','--onboarding-config',str(onboarding))
        assert r.returncode==0, r.stdout+r.stderr
        init=json.loads(r.stdout); assert init['nextStage']=='github-infrastructure-audit' and init['currentSourceHeadSha']=='a'*40 and init['authorizedOperatorIds']==['12345'] and init['authorizedOperatorLogins']==['release-operator']
        data=json.loads(ledger.read_text()); assert data['onboardingConfigSha256']==cfg['configSha256'] and data['currentSourceHeadSha']=='a'*40

        r=run('record','--ledger',str(ledger),'--stage','github-infrastructure-audit')
        assert r.returncode!=0 and 'record-run' in r.stdout

        run_snapshot(runs/'101.json',101,'.github/workflows/production-execution-readiness.yml','a'*40)
        for stage in ['github-infrastructure-audit','live-runner-readiness']:
            r=run('record-run','--ledger',str(ledger),'--stage',stage,'--run-id','101','--snapshot-dir',str(runs),'--intent-nonce','mte-test-intent-0001'); assert r.returncode==0, r.stdout+r.stderr
        run_snapshot(runs/'102.json',102,'.github/workflows/qualify-production-ml-self-hosted.yml','a'*40,title='Production qualification / prepare')
        r=run('record-run','--ledger',str(ledger),'--stage','qualification-prepare','--run-id','102','--snapshot-dir',str(runs),'--intent-nonce','mte-test-intent-0001'); assert r.returncode==0
        r=run('record','--ledger',str(ledger),'--stage','benchmark-review','--manual-reviewed'); assert r.returncode!=0 and 'record-manual' in r.stdout
        manual_fixture=load_module(MANUAL_SMOKE,'manual_fixture_for_handoff')
        manual=load_module(MANUAL_TOOL,'manual_tool_for_handoff_fixture')
        run_plan=td/'ready-run-plan.json'; benchmark_review=td/'benchmark-review.json'; manual_fixture.benchmark(run_plan,benchmark_review)
        checkpoint_path=td/'benchmark-checkpoint.json'
        ledger_data=json.loads(ledger.read_text())
        ev={'run-plan':run_plan,'benchmark-review':benchmark_review}
        semantic=manual.validate_benchmark_review(ev)
        cp=manual.create_checkpoint(stage='benchmark-review',ledger=ledger_data,evidence=ev,actor={'id':'12345','login':'release-operator'},semantic=semantic)
        checkpoint_path.write_text(json.dumps(cp,indent=2)+'\n')
        actor_snapshot=td/'actor-snapshot.json'; actor_snapshot.write_text(json.dumps({'actor':{'id':'12345','login':'release-operator'},'repositoryId':123,'defaultBranch':'main','defaultBranchHeadSha':'a'*40}))
        r=run('record-manual','--ledger',str(ledger),'--stage','benchmark-review','--checkpoint',str(checkpoint_path),'--evidence',f'run-plan={run_plan}','--evidence',f'benchmark-review={benchmark_review}','--actor-snapshot',str(actor_snapshot)); assert r.returncode==0, r.stdout+r.stderr
        run_snapshot(runs/'103.json',103,'.github/workflows/qualify-production-ml-self-hosted.yml','a'*40,title='Production qualification / execute')
        r=run('record-run','--ledger',str(ledger),'--stage','qualification-execute','--run-id','103','--snapshot-dir',str(runs),'--intent-nonce','mte-test-intent-0001'); assert r.returncode==0
        run_snapshot(runs/'104.json',104,'.github/workflows/promote-production-qualification.yml','a'*40)
        qual_files=contract['firstRealRun']['sourceTransitionAllowlists']['qualification-evidence']['paths']
        qual_branch='qualification-evidence/run-103-mte-test-intent-0001'; qual_head='d'*40
        created_pr_snapshot(td/'pr-created.json',1,'a'*40,qual_head,qual_branch,qual_files)
        r=run('record-run','--ledger',str(ledger),'--stage','qualification-evidence-pr-created','--run-id','104','--snapshot-dir',str(runs),'--intent-nonce','mte-test-intent-0001','--pr-created-snapshot',str(td/'pr-created.json')); assert r.returncode==0, r.stdout+r.stderr

        pr_snapshot(td/'pr1.json',1,'a'*40,'b'*40,qual_head,qual_branch,qual_files)
        r=run('record-pr-merge','--ledger',str(ledger),'--stage','qualification-evidence-pr-merged','--pr-number','1','--snapshot',str(td/'pr1.json')); assert r.returncode==0, r.stdout+r.stderr
        assert json.loads(r.stdout)['currentSourceHeadSha']=='b'*40
        # Checkout reconciliation is controller-only; inject a validated fixture record so offline handoff tests can continue.
        ld=json.loads(ledger.read_text()); handoff.append_record(ld,'qualification-evidence-checkout-reconciled',checkoutReconciliation={'revision':'rev31-post-merge-checkout-reconciliation-v1','reconciledHeadSha':'b'*40,'mergeStage':'qualification-evidence-pr-merged','reviewedChangedPaths':qual_files,'sourceIntegrityManifestSha256':'9'*64}); handoff.write(ledger,ld)

        workflows=contract['firstRealRun']['stageLaunchHints']['exact-artifact-builds']['workflows']
        ids=[]
        for i,wf in enumerate(workflows,201):
            run_snapshot(runs/f'{i}.json',i,wf,'b'*40); ids += ['--run-id',str(i)]
        r=run('record-run','--ledger',str(ledger),'--stage','exact-artifact-builds',*ids,'--snapshot-dir',str(runs),'--intent-nonce','mte-test-intent-0001'); assert r.returncode==0, r.stdout+r.stderr

        # Unauthorized actor is rejected by live-run provenance logic.
        other=td/'other-ledger.json'
        r=run('init','--output',str(other),'--release-id','v1.0.0-rc2','--release-class','private-v1','--onboarding-config',str(onboarding)); assert r.returncode==0
        run_snapshot(runs/'999.json',999,'.github/workflows/production-execution-readiness.yml','a'*40,actor='intruder',actor_id='99999')
        r=run('record-run','--ledger',str(other),'--stage','github-infrastructure-audit','--run-id','999','--snapshot-dir',str(runs),'--intent-nonce','mte-test-intent-0001'); assert r.returncode!=0 and 'actor id is not' in r.stdout


        # Run-intent mismatch is rejected even when every other run field is valid.
        nonce_ledger=td/'nonce-ledger.json'
        r=run('init','--output',str(nonce_ledger),'--release-id','v1.0.0-rc3','--release-class','private-v1','--onboarding-config',str(onboarding)); assert r.returncode==0
        run_snapshot(runs/'998.json',998,'.github/workflows/production-execution-readiness.yml','a'*40,nonce='mte-actual-intent-998')
        r=run('record-run','--ledger',str(nonce_ledger),'--stage','github-infrastructure-audit','--run-id','998','--snapshot-dir',str(runs),'--intent-nonce','mte-different-intent-998')
        assert r.returncode!=0 and 'intent nonce' in r.stdout

        # Public plan includes Store and post-Store source transition stages before finalization.
        public=td/'public-ledger.json'
        r=run('init','--output',str(public),'--release-id','v1.0.0','--release-class','public-v1','--onboarding-config',str(onboarding)); assert r.returncode==0
        pub=json.loads(public.read_text())
        plan=contract['firstRealRun']['stagePlans']['public-v1']
        assert 'store-candidate' in plan and 'store-installed-chrome-smoke' in plan and 'public-evidence-pr-merged' in plan
        assert plan.index('public-evidence-pr-merged') < plan.index('public-evidence-checkout-reconciled') < plan.index('final-release-gate-and-capsule')

        data=json.loads(ledger.read_text()); data['records'][0]['status']='failed'; ledger.write_text(json.dumps(data))
        r=run('status','--ledger',str(ledger)); assert r.returncode!=0 and 'ledgerSha256 mismatch' in r.stdout

        bad=td/'bad-onboarding.json'; bad_data=json.loads(onboarding.read_text()); bad_data['repositoryBinding']['defaultBranchHeadSha']='c'*40; bad.write_text(json.dumps(bad_data))
        r=run('init','--output',str(td/'bad-ledger.json'),'--release-id','v1.0.1','--release-class','private-v1','--onboarding-config',str(bad)); assert r.returncode!=0 and 'onboarding config is not valid/bound' in r.stdout
    print('First real run handoff tooling: 11/11 passed')
    return 0
if __name__=='__main__': raise SystemExit(main())
