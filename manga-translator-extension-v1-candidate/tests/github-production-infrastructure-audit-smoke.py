from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'scripts' / 'audit_github_production_infrastructure.py'
CONTRACT = ROOT / 'release-control' / 'production-execution-contract.json'


def run(snapshot: Path, *extra: str):
    return subprocess.run(
        [sys.executable, str(AUDIT), '--snapshot', str(snapshot), *extra],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def fixture(contract: dict) -> dict:
    envs = {}
    for name in contract['protectedEnvironments']:
        envs[name] = {
            'protectionRules': [{
                'type': 'required_reviewers',
                'prevent_self_review': True,
                'reviewers': [{'type': 'User', 'reviewer': {'login': 'release-reviewer'}}],
            }],
            'deploymentBranchPolicy': {'protected_branches': False, 'custom_branch_policies': True},
            'deploymentBranchPolicies': [{'id': 1, 'name': 'main', 'type': 'branch'}],
            'variables': [],
            'secrets': [],
        }
    audit_cfg = contract['githubInfrastructureAudit']
    envs[audit_cfg['repositoryAuditEnvironment']]['secrets'] = sorted(set(envs[audit_cfg['repositoryAuditEnvironment']]['secrets']) | {audit_cfg['repositoryAuditSecret']})
    for role in contract['selfHostedRoles']:
        env = envs[role['environment']]
        env['variables'] = sorted(set(env['variables']) | set(role.get('requiredVariables', [])))
        env['secrets'] = sorted(set(env['secrets']) | set(role.get('requiredSecrets', [])))
    for platform_name in ('macos', 'windows'):
        signing = contract['publicSigning'][platform_name]
        env = envs[signing['environment']]
        env['variables'] = sorted(set(env['variables']) | set(signing.get('requiredVariables', [])))
        env['secrets'] = sorted(set(env['secrets']) | set(signing.get('requiredSecrets', [])))
    runners = []
    for index, role in enumerate(contract['selfHostedRoles'], start=1):
        runners.append({
            'id': index,
            'name': f'runner-{index}',
            'os': role['os'].lower(),
            'status': 'online',
            'busy': False,
            'ephemeral': False,
            'version': 'fixture',
            'labels': role['labels'],
        })
    return {'schemaVersion': 2, 'repository': 'owner/repo', 'repositoryId': 123, 'defaultBranch': 'main', 'repositoryVariables': {contract['workflowTrust']['operatorAllowlistVariable']: '[\"12345\"]'}, 'runners': runners, 'environments': envs}


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory(prefix='mte-github-infra-audit-') as td:
        td = Path(td)
        good = fixture(contract)
        path = td / 'good.json'; path.write_text(json.dumps(good), encoding='utf-8')
        result = run(path, '--strict')
        assert result.returncode == 0, result.stdout + result.stderr
        report = json.loads(result.stdout)
        assert report['passed'] is True and report['blockingFailureCount'] == 0

        no_operator = fixture(contract)
        no_operator['repositoryVariables'] = {}
        path = td / 'no-operator.json'; path.write_text(json.dumps(no_operator), encoding='utf-8')
        result = run(path, '--strict')
        assert result.returncode != 0
        assert any(x['name'].startswith('repository-variable:MTE_PRODUCTION_OPERATOR_ID_ALLOWLIST_JSON') and not x['passed'] for x in json.loads(result.stdout)['checks'])

        no_runner = fixture(contract)
        no_runner['runners'] = [x for x in no_runner['runners'] if 'mte-production-qualification' not in x['labels']]
        path = td / 'no-runner.json'; path.write_text(json.dumps(no_runner), encoding='utf-8')
        result = run(path, '--strict')
        assert result.returncode != 0
        report = json.loads(result.stdout)
        assert any(x['name'] == 'runner:qualification-linux-x86_64' and not x['passed'] for x in report['checks'])

        no_secret = fixture(contract)
        env = no_secret['environments']['release-smoke-linux']
        env['secrets'] = [x for x in env['secrets'] if x != 'MTE_OPENAI_API_KEY']
        path = td / 'no-secret.json'; path.write_text(json.dumps(no_secret), encoding='utf-8')
        result = run(path, '--strict')
        assert result.returncode != 0
        assert 'MTE_OPENAI_API_KEY' not in ''.join(str(x.get('actual', '')) for x in json.loads(result.stdout)['checks'])

        no_audit_secret = fixture(contract)
        audit_cfg = contract['githubInfrastructureAudit']
        audit_env = no_audit_secret['environments'][audit_cfg['repositoryAuditEnvironment']]
        audit_env['secrets'] = [x for x in audit_env['secrets'] if x != audit_cfg['repositoryAuditSecret']]
        path = td / 'no-audit-secret.json'; path.write_text(json.dumps(no_audit_secret), encoding='utf-8')
        result = run(path, '--strict')
        assert result.returncode != 0
        assert any(x['name'] == f"environment-secret:{audit_cfg['repositoryAuditEnvironment']}:{audit_cfg['repositoryAuditSecret']}" and not x['passed'] for x in json.loads(result.stdout)['checks'])

        wrong_branch = fixture(contract)
        wrong_branch['environments']['production-qualification']['deploymentBranchPolicies'] = [{'id': 2, 'name': 'release', 'type': 'branch'}]
        path = td / 'wrong-branch.json'; path.write_text(json.dumps(wrong_branch), encoding='utf-8')
        result = run(path, '--strict')
        assert result.returncode != 0
        assert any(x['name'] == 'environment-default-branch-only:production-qualification' and not x['passed'] for x in json.loads(result.stdout)['checks'])

        # Live collector pagination must not stop at the first page.
        spec = importlib.util.spec_from_file_location('mte_infra_audit', AUDIT)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        calls = []
        def fake_get(url, token, api_version):
            calls.append(url)
            if url == 'https://api.github.com/repos/owner/repo':
                return {'id': 123, 'full_name': 'owner/repo', 'default_branch': 'main'}
            if '/actions/runners' in url:
                page = 2 if 'page=2' in url else 1
                batch = [{'id': i, 'name': f'r{i}', 'status': 'online', 'busy': False, 'labels': []} for i in range(100)] if page == 1 else [{'id': 101, 'name': 'r101', 'status': 'online', 'busy': False, 'labels': []}]
                return {'total_count': 101, 'runners': batch}
            if '/actions/variables?' in url:
                return {'total_count':1, 'variables':[{'name':'MTE_PRODUCTION_OPERATOR_ID_ALLOWLIST_JSON','value':'[\"12345\"]'}]}
            if '/environments?' in url:
                return {'total_count': 1, 'environments': [{'name':'production-qualification','deployment_branch_policy':{'protected_branches':False,'custom_branch_policies':True}}]}
            if '/deployment-branch-policies?' in url:
                return {'total_count':1, 'branch_policies':[{'id':1,'name':'main','type':'branch'}]}
            if '/variables?' in url:
                page = 2 if 'page=2' in url else 1
                batch = [{'name':f'V{i}'} for i in range(30)] if page == 1 else [{'name':'V30'}]
                return {'total_count':31, 'variables':batch}
            if '/secrets?' in url:
                return {'total_count':0, 'secrets':[]}
            raise AssertionError(url)
        module.api_get = fake_get
        snap = module.collect_live_snapshot('owner/repo', 'token', contract)
        assert len(snap['runners']) == 101
        assert snap['repositoryVariables']['MTE_PRODUCTION_OPERATOR_ID_ALLOWLIST_JSON']=='[\"12345\"]'
        assert len(snap['environments']['production-qualification']['variables']) == 31
        assert any('page=2' in url and '/actions/runners' in url for url in calls)
        assert any('page=2' in url and '/variables?' in url for url in calls)

        warning_only = fixture(contract)
        for env in warning_only['environments'].values():
            env['protectionRules'] = []
        path = td / 'warning.json'; path.write_text(json.dumps(warning_only), encoding='utf-8')
        result = run(path, '--strict')
        report = json.loads(result.stdout)
        assert result.returncode == 0 and report['passed'] is True and report['warningCount'] > 0

    print('GitHub production infrastructure audit tooling: 8/8 passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
