from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / 'release-control' / 'production-execution-contract.json'


class AuditError(ValueError):
    pass


def load_contract(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('schemaVersion') != 4 or value.get('revision') != 'rev34-recovery-rotation-offsite-durability-v1':
        raise AuditError('production execution contract schema/revision is unsupported')
    return value


def api_get(url: str, token: str, api_version: str) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            'Accept': 'application/vnd.github+json',
            'Authorization': f'Bearer {token}',
            'X-GitHub-Api-Version': api_version,
            'User-Agent': 'mte-production-infrastructure-audit',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')[:500]
        raise AuditError(f'GitHub API request failed with HTTP {exc.code}: {body}') from exc
    except urllib.error.URLError as exc:
        raise AuditError(f'GitHub API request failed: {exc.reason}') from exc




def api_get_paginated(url: str, token: str, api_version: str, collection_key: str, *, per_page: int = 100) -> list[dict[str, Any]]:
    if per_page < 1 or per_page > 100:
        raise AuditError('per_page must be between 1 and 100')
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        separator = '&' if '?' in url else '?'
        payload = api_get(f"{url}{separator}per_page={per_page}&page={page}", token, api_version)
        batch = payload.get(collection_key, [])
        if not isinstance(batch, list):
            raise AuditError(f'GitHub API response missing list collection: {collection_key}')
        items.extend(x for x in batch if isinstance(x, dict))
        total = payload.get('total_count')
        if isinstance(total, int) and len(items) >= total:
            break
        if len(batch) < per_page:
            break
        page += 1
        if page > 10000:
            raise AuditError(f'pagination safety limit exceeded for {collection_key}')
    return items

def collect_live_snapshot(repository: str, token: str, contract: dict[str, Any]) -> dict[str, Any]:
    if repository.count('/') != 1:
        raise AuditError('--repository must be OWNER/REPO')
    owner, repo = repository.split('/', 1)
    base = f'https://api.github.com/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}'
    api_version = contract['githubInfrastructureAudit']['apiVersion']
    repository_meta = api_get(base, token, api_version)
    repository_id = repository_meta.get('id')
    default_branch = str(repository_meta.get('default_branch', ''))
    full_name = str(repository_meta.get('full_name', ''))
    if not isinstance(repository_id, int) or not default_branch or full_name.lower() != repository.lower():
        raise AuditError('GitHub repository metadata is missing or does not match --repository')

    runner_items = api_get_paginated(f'{base}/actions/runners', token, api_version, 'runners', per_page=100)
    env_items = api_get_paginated(f'{base}/environments', token, api_version, 'environments', per_page=100)
    repository_variable_items = api_get_paginated(f'{base}/actions/variables', token, api_version, 'variables', per_page=30)
    environments: dict[str, Any] = {}
    for env in env_items:
        name = str(env.get('name', ''))
        if not name:
            continue
        encoded = urllib.parse.quote(name, safe='')
        variable_items = api_get_paginated(f'{base}/environments/{encoded}/variables', token, api_version, 'variables', per_page=30)
        secret_items = api_get_paginated(f'{base}/environments/{encoded}/secrets', token, api_version, 'secrets', per_page=100)
        deployment_policy = env.get('deployment_branch_policy')
        branch_policies: list[dict[str, Any]] = []
        if isinstance(deployment_policy, dict) and deployment_policy.get('custom_branch_policies') is True:
            branch_policies = api_get_paginated(
                f'{base}/environments/{encoded}/deployment-branch-policies',
                token,
                api_version,
                'branch_policies',
                per_page=100,
            )
        environments[name] = {
            'protectionRules': env.get('protection_rules', []),
            'deploymentBranchPolicy': deployment_policy,
            'deploymentBranchPolicies': [
                {'id': item.get('id'), 'name': item.get('name'), 'type': item.get('type')}
                for item in branch_policies if item.get('name')
            ],
            'variables': sorted(str(v.get('name')) for v in variable_items if v.get('name')),
            'secrets': sorted(str(v.get('name')) for v in secret_items if v.get('name')),
        }
    runners = []
    for item in runner_items:
        runners.append({
            'id': item.get('id'),
            'name': item.get('name'),
            'os': item.get('os'),
            'status': item.get('status'),
            'busy': bool(item.get('busy')),
            'ephemeral': bool(item.get('ephemeral')),
            'version': item.get('version'),
            'labels': sorted(str(x.get('name')) for x in item.get('labels', []) if x.get('name')),
        })
    return {
        'schemaVersion': 2,
        'repository': repository,
        'repositoryId': repository_id,
        'defaultBranch': default_branch,
        'repositoryVariables': {str(v.get('name')): str(v.get('value', '')) for v in repository_variable_items if v.get('name')},
        'runners': runners,
        'environments': environments,
    }


def required_environment_names(contract: dict[str, Any]) -> set[str]:
    names = set(contract['protectedEnvironments'])
    names.update(role['environment'] for role in contract['selfHostedRoles'])
    names.add(contract['publicSigning']['macos']['environment'])
    names.add(contract['publicSigning']['windows']['environment'])
    return names


def default_branch_only_policy(env: dict[str, Any], default_branch: str) -> bool:
    deployment = env.get('deploymentBranchPolicy')
    if not isinstance(deployment, dict):
        return False
    if deployment.get('protected_branches') is not False or deployment.get('custom_branch_policies') is not True:
        return False
    policies = env.get('deploymentBranchPolicies') or []
    if len(policies) != 1:
        return False
    policy = policies[0]
    policy_type = policy.get('type')
    return str(policy.get('name', '')) == default_branch and policy_type in (None, '', 'branch')


def audit_snapshot(snapshot: dict[str, Any], contract: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    cfg = contract['githubInfrastructureAudit']
    environments = snapshot.get('environments') or {}
    runners = snapshot.get('runners') or []
    default_branch = str(snapshot.get('defaultBranch', ''))
    checks.append({'name': 'repository-default-branch', 'passed': bool(default_branch), 'severity': 'error', 'actual': default_branch or None})
    trust = contract.get('workflowTrust') or {}
    operator_var = str(trust.get('operatorAllowlistVariable', ''))
    raw_allowlist = (snapshot.get('repositoryVariables') or {}).get(operator_var, '') if operator_var else ''
    operators: list[str] = []
    valid_allowlist = False
    if raw_allowlist:
        try:
            parsed = json.loads(raw_allowlist)
            if isinstance(parsed, list) and parsed and all(isinstance(x, str) and x.isdigit() for x in parsed):
                operators = parsed
                valid_allowlist = len(set(parsed)) == len(parsed)
        except json.JSONDecodeError:
            pass
    if operator_var:
        checks.append({'name': f'repository-variable:{operator_var}', 'passed': valid_allowlist, 'severity': 'error', 'operatorCount': len(operators)})

    for env_name in sorted(required_environment_names(contract)):
        present = env_name in environments
        checks.append({'name': f'environment:{env_name}', 'passed': present, 'severity': 'error'})
        if not present:
            continue
        env = environments[env_name]
        rules = env.get('protectionRules') or []
        reviewer_rules = [x for x in rules if x.get('type') == 'required_reviewers']
        expected = contract['protectedEnvironments'].get(env_name, {})
        if expected.get('recommendedRequiredReviewer'):
            ok = bool(reviewer_rules and any((x.get('reviewers') or []) for x in reviewer_rules))
            checks.append({
                'name': f'environment-required-reviewer:{env_name}',
                'passed': ok,
                'severity': 'error' if cfg.get('protectionRecommendationsAreBlocking') else 'warning',
            })
        if expected.get('preventSelfReviewRecommended'):
            ok = bool(reviewer_rules and any(bool(x.get('prevent_self_review')) for x in reviewer_rules))
            checks.append({
                'name': f'environment-prevent-self-review:{env_name}',
                'passed': ok,
                'severity': 'error' if cfg.get('protectionRecommendationsAreBlocking') else 'warning',
            })
        if cfg.get('requireDefaultBranchOnlyEnvironments') or expected.get('requiredDeploymentBranchPolicy') == 'default-branch-only':
            ok = bool(default_branch) and default_branch_only_policy(env, default_branch)
            checks.append({
                'name': f'environment-default-branch-only:{env_name}',
                'passed': ok,
                'severity': 'error',
                'expectedBranch': default_branch or None,
            })

    audit_env_name = str(cfg.get('repositoryAuditEnvironment', ''))
    audit_secret_name = str(cfg.get('repositoryAuditSecret', ''))
    if audit_env_name and audit_secret_name:
        audit_env = environments.get(audit_env_name, {})
        checks.append({
            'name': f'environment-secret:{audit_env_name}:{audit_secret_name}',
            'passed': audit_secret_name in set(audit_env.get('secrets') or []),
            'severity': 'error',
            'sensitive': True,
        })

    for role in contract['selfHostedRoles']:
        required_labels = {str(x).lower() for x in role['labels']}
        matches = []
        for runner in runners:
            labels = {str(x).lower() for x in runner.get('labels', [])}
            if required_labels.issubset(labels):
                matches.append(runner)
        online = [x for x in matches if str(x.get('status')).lower() == 'online']
        eligible = online
        if cfg.get('requireIdleRunnerPerRole'):
            eligible = [x for x in online if not x.get('busy')]
        checks.append({
            'name': f'runner:{role["role"]}',
            'passed': bool(eligible),
            'severity': 'error',
            'requiredLabels': role['labels'],
            'matchingRunnerNames': [x.get('name') for x in matches],
            'onlineRunnerNames': [x.get('name') for x in online],
        })
        env = environments.get(role['environment'], {})
        variable_names = set(env.get('variables') or [])
        secret_names = set(env.get('secrets') or [])
        for name in role.get('requiredVariables', []):
            checks.append({'name': f'environment-variable:{role["environment"]}:{name}', 'passed': name in variable_names, 'severity': 'error'})
        for name in role.get('requiredSecrets', []):
            checks.append({'name': f'environment-secret:{role["environment"]}:{name}', 'passed': name in secret_names, 'severity': 'error', 'sensitive': True})

    for platform_name in ('macos', 'windows'):
        signing = contract['publicSigning'][platform_name]
        env = environments.get(signing['environment'], {})
        variable_names = set(env.get('variables') or [])
        secret_names = set(env.get('secrets') or [])
        for name in signing.get('requiredVariables', []):
            checks.append({'name': f'environment-variable:{signing["environment"]}:{name}', 'passed': name in variable_names, 'severity': 'error'})
        for name in signing.get('requiredSecrets', []):
            checks.append({'name': f'environment-secret:{signing["environment"]}:{name}', 'passed': name in secret_names, 'severity': 'error', 'sensitive': True})

    return checks


def sanitized_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    # The GitHub endpoints used here expose secret names, never encrypted/plaintext values.
    return {
        'schemaVersion': 2,
        'repository': snapshot.get('repository'),
        'repositoryId': snapshot.get('repositoryId'),
        'defaultBranch': snapshot.get('defaultBranch'),
        'repositoryVariableNames': sorted((snapshot.get('repositoryVariables') or {}).keys()),
        'runners': snapshot.get('runners', []),
        'environments': {
            name: {
                'protectionRules': data.get('protectionRules', []),
                'deploymentBranchPolicy': data.get('deploymentBranchPolicy'),
                'deploymentBranchPolicies': data.get('deploymentBranchPolicies', []),
                'variables': sorted(data.get('variables', [])),
                'secrets': sorted(data.get('secrets', [])),
            }
            for name, data in sorted((snapshot.get('environments') or {}).items())
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Audit GitHub-side production runners/environments/variable and secret names without reading secret values.')
    parser.add_argument('--contract', type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument('--repository', help='OWNER/REPO for live GitHub audit')
    parser.add_argument('--token-env', default='MTE_INFRA_AUDIT_TOKEN')
    parser.add_argument('--snapshot', type=Path, help='Offline GitHub metadata snapshot for deterministic tests')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--strict', action='store_true')
    args = parser.parse_args()

    contract = load_contract(args.contract.resolve())
    try:
        if args.snapshot:
            snapshot = json.loads(args.snapshot.read_text(encoding='utf-8'))
        else:
            if not args.repository:
                raise AuditError('--repository is required for a live audit')
            token = os.environ.get(args.token_env, '').strip()
            if not token:
                raise AuditError(f'{args.token_env} is required for a live audit')
            snapshot = collect_live_snapshot(args.repository, token, contract)
        checks = audit_snapshot(snapshot, contract)
        blocking_failures = [x for x in checks if x.get('severity') == 'error' and not x.get('passed')]
        warnings = [x for x in checks if x.get('severity') == 'warning' and not x.get('passed')]
        report = {
            'schemaVersion': 1,
            'revision': contract['revision'],
            'repository': snapshot.get('repository'),
            'passed': not blocking_failures,
            'blockingFailureCount': len(blocking_failures),
            'warningCount': len(warnings),
            'checks': checks,
            'observed': sanitized_snapshot(snapshot),
        }
    except AuditError as exc:
        report = {
            'schemaVersion': 1,
            'revision': contract['revision'],
            'repository': args.repository,
            'passed': False,
            'blockingFailureCount': 1,
            'warningCount': 0,
            'checks': [{'name': 'github-api-audit', 'passed': False, 'severity': 'error', 'error': str(exc)}],
            'observed': None,
        }

    payload = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding='utf-8')
    print(payload, end='')
    return 2 if args.strict and not report['passed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
