from __future__ import annotations
import importlib.util, os, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TOOL=ROOT/'scripts'/'provision_github_production_infrastructure.py'
CONTRACT=ROOT/'release-control'/'production-execution-contract.json'
spec=importlib.util.spec_from_file_location('mte_provision',TOOL)
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


def main():
    contract=module.load_contract(CONTRACT)
    with tempfile.TemporaryDirectory(prefix='mte-provision-') as td:
        td=Path(td)
        cfg=module.render_template(contract,CONTRACT,'owner/repo')
        module.validate_config(cfg,contract,CONTRACT)
        assert cfg['repositoryBinding'] is None and cfg['productionOperators']==[]
        assert any('MTE_OPENAI_API_KEY' in env for env in cfg['environmentSecrets'].values())
        assert 'MTE_INFRA_AUDIT_TOKEN' in cfg['environmentSecrets']['production-infrastructure-audit']
        assert all(set(entry)=={'sourceEnv'} for env in cfg['environmentSecrets'].values() for entry in env.values())

        try: module.validate_config(cfg,contract,CONTRACT,require_binding=True)
        except module.ProvisionError as exc: assert ('production operator' in str(exc) or 'repository-bound' in str(exc))
        else: raise AssertionError('live operations must require binding')

        plan=module.build_plan(cfg,contract)
        assert plan['missingSourceCount']>0
        assert not any('value' in action for action in plan['actions'] if action['type']=='environment-secret-set')

        for env,names in cfg['environmentVariables'].items():
            for name,meta in names.items(): os.environ[meta['sourceEnv']]=f'/safe/{env}/{name}'
        for env,names in cfg['environmentSecrets'].items():
            for name,meta in names.items(): os.environ[meta['sourceEnv']]='fixture-secret'
        plan=module.build_plan(cfg,contract)
        assert plan['missingSourceCount']==0

        for i,role in enumerate(contract['selfHostedRoles'],1):
            cfg=module.set_runner_name(cfg,contract,role['role'],f'runner-{i}')
        cfg=module.set_operator(cfg,'release-operator')
        assert cfg['productionOperators']==['release-operator']
        module.validate_config(cfg,contract,CONTRACT)
        old_live, old_git, old_resolve = module.live_repository_identity, module.git_output, module.resolve_operator
        try:
            module.live_repository_identity=lambda repository,token,contract:{'repositoryId':123,'fullName':'owner/repo','defaultBranch':'main','defaultBranchHeadSha':'a'*40}
            module.resolve_operator=lambda login,token,contract:{'login':'release-operator','id':'12345'}
            def fake_git(*args):
                if args==('rev-parse','HEAD'): return 'a'*40
                if args==('branch','--show-current'): return 'main'
                if args==('remote','get-url','origin'): return 'git@github.com:owner/repo.git'
                raise AssertionError(args)
            module.git_output=fake_git
            cfg=module.bind_config(cfg,contract,CONTRACT,'fixture-token')
        finally:
            module.live_repository_identity, module.git_output, module.resolve_operator = old_live, old_git, old_resolve
        module.validate_config(cfg,contract,CONTRACT,require_binding=True)
        assert cfg['repositoryBinding']['repositoryId']==123 and cfg['repositoryBinding']['authorizedOperators']==[{'login':'release-operator','id':'12345'}]
        assert cfg['repositoryBinding']['workflowSetSha256']==module.workflow_set_sha256(contract)

        cmd=module.runner_command(cfg,contract,'qualification-linux-x86_64')
        assert 'registration-token' in cmd['command'] and 'mte-production-qualification' in cmd['command']
        assert 'TOKEN=' in cmd['command'] and 'Bearer' not in cmd['command']
        assert cmd['boundSourceHeadSha']=='a'*40

        snapshot={'schemaVersion':2,'repository':'owner/repo','repositoryId':123,'defaultBranch':'main','repositoryVariables':{contract['workflowTrust']['operatorAllowlistVariable']:module.operator_allowlist_json(cfg)},'environments':{name:{'deploymentBranchPolicy':{'protected_branches':False,'custom_branch_policies':True},'deploymentBranchPolicies':[{'id':1,'name':'main','type':'branch'}]} for name in contract['protectedEnvironments']},'runners':[
          {'id':i,'name':cfg['runnerNames'][role['role']],'labels':role['labels'],'status':'online','busy':False}
          for i,role in enumerate(contract['selfHostedRoles'],1)
        ]}
        plan=module.build_plan(cfg,contract,snapshot)
        assert all(a['needed'] is False for a in plan['actions'] if a['type']=='environment-create-if-missing')
        assert all(a['runnerPresent'] is True for a in plan['actions'] if a['type']=='runner-label-add')
        assert any(a['type']=='repository-variable-set' and a['needed'] is False for a in plan['actions'])

        assert plan['blockingPolicyCount']==0
        assert all(a.get('needed') is False for a in plan['actions'] if a['type']=='environment-default-branch-policy')
        bad_snapshot={**snapshot,'environments':dict(snapshot['environments'])}
        bad_snapshot['environments']['release-candidate']={'deploymentBranchPolicy':{'protected_branches':True,'custom_branch_policies':False},'deploymentBranchPolicies':[]}
        bad_plan=module.build_plan(cfg,contract,bad_snapshot)
        assert bad_plan['blockingPolicyCount']==1

        old_live=module.live_repository_identity
        try:
            module.live_repository_identity=lambda repository,token,contract:{'repositoryId':123,'fullName':'owner/repo','defaultBranch':'main','defaultBranchHeadSha':'b'*40}
            try: module.verify_live_binding(cfg,contract,'fixture-token')
            except module.ProvisionError as exc: assert 'defaultBranchHeadSha' in str(exc)
            else: raise AssertionError('default-branch drift must fail')
        finally: module.live_repository_identity=old_live

        for bad_repo in ['owner/repo;touch-pwned','owner/../repo','owner/repo extra']:
            try: module.render_template(contract,CONTRACT,bad_repo)
            except module.ProvisionError: pass
            else: raise AssertionError('unsafe repository identifier must fail')

        unsafe=dict(cfg); unsafe['runnerNames']=dict(cfg['runnerNames']); unsafe['runnerNames']['qualification-linux-x86_64']='runner;echo-pwned'; unsafe=module.seal_config(unsafe)
        try: module.validate_config(unsafe,contract,CONTRACT,require_binding=True)
        except module.ProvisionError as exc: assert 'runner name' in str(exc)
        else: raise AssertionError('unsafe runner name must fail')

        unbound=module.render_template(contract,CONTRACT,'owner/repo')
        try: module.set_operator(unbound,'bad;operator')
        except module.ProvisionError: pass
        else: raise AssertionError('unsafe production operator login must fail')

        tampered=dict(cfg); tampered['repository']='evil/repo'
        try: module.validate_config(tampered,contract,CONTRACT)
        except module.ProvisionError as exc: assert 'configSha256 mismatch' in str(exc)
        else: raise AssertionError('tamper must fail')
    print('Production infrastructure bootstrap tooling: 11/11 passed')
    return 0
if __name__=='__main__': raise SystemExit(main())
