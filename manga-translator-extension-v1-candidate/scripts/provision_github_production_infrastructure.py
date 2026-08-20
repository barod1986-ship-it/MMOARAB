from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / 'release-control' / 'production-execution-contract.json'
SOURCE_INTEGRITY = ROOT / 'SOURCE_SHA256SUMS.txt'
BOOTSTRAP_REVISION = 'rev27-github-production-infrastructure-bootstrap-v4'
CONTRACT_REVISION = 'rev34-recovery-rotation-offsite-durability-v1'
REPOSITORY_RE = re.compile(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')
RUNNER_NAME_RE = re.compile(r'^[A-Za-z0-9._-]{1,100}$')
GITHUB_LOGIN_RE = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$')
SHA_RE = re.compile(r'^[0-9a-f]{40}$')


class ProvisionError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_contract(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('schemaVersion') != 4 or value.get('revision') != CONTRACT_REVISION:
        raise ProvisionError('production execution contract schema/revision is unsupported')
    return value


def source_env_name(kind: str, environment: str, name: str) -> str:
    def clean(text: str) -> str:
        return ''.join(ch if ch.isalnum() else '_' for ch in text.upper())
    return f'MTE_BOOTSTRAP_{kind}_{clean(environment)}__{clean(name)}'


def validate_repository_name(repository: str) -> None:
    if not REPOSITORY_RE.fullmatch(repository) or repository.startswith('.') or '/.' in repository:
        raise ProvisionError('bootstrap repository must be a conservative OWNER/REPO identifier')


def validate_runner_name(name: str, role: str) -> None:
    if name.startswith('__SET_RUNNER_NAME__'):
        return
    if not RUNNER_NAME_RE.fullmatch(name):
        raise ProvisionError(f'runner name for {role} must match {RUNNER_NAME_RE.pattern}')


def required_names(contract: dict[str, Any]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    variables: dict[str, set[str]] = {name: set() for name in contract['protectedEnvironments']}
    secrets: dict[str, set[str]] = {name: set() for name in contract['protectedEnvironments']}
    for role in contract['selfHostedRoles']:
        variables.setdefault(role['environment'], set()).update(role.get('requiredVariables', []))
        secrets.setdefault(role['environment'], set()).update(role.get('requiredSecrets', []))
    for platform in ('macos', 'windows'):
        cfg = contract['publicSigning'][platform]
        variables.setdefault(cfg['environment'], set()).update(cfg.get('requiredVariables', []))
        secrets.setdefault(cfg['environment'], set()).update(cfg.get('requiredSecrets', []))
    audit_cfg = contract['githubInfrastructureAudit']
    audit_env = str(audit_cfg.get('repositoryAuditEnvironment', ''))
    audit_secret = str(audit_cfg.get('repositoryAuditSecret', ''))
    if not audit_env or audit_env not in contract['protectedEnvironments'] or not audit_secret:
        raise ProvisionError('GitHub infrastructure audit environment/secret contract is incomplete')
    secrets.setdefault(audit_env, set()).add(audit_secret)
    return variables, secrets


def expected_workflow_paths(contract: dict[str, Any]) -> list[str]:
    paths = contract.get('repositoryOnboarding', {}).get('expectedWorkflowPaths') or []
    if not paths or len(paths) != len(set(paths)):
        raise ProvisionError('repository onboarding workflow path set is empty or duplicated')
    return [str(x) for x in paths]


def workflow_set_manifest(contract: dict[str, Any]) -> dict[str, str]:
    manifest: dict[str, str] = {}
    for rel in expected_workflow_paths(contract):
        path = ROOT / rel
        if not path.is_file():
            raise ProvisionError(f'expected production workflow is missing locally: {rel}')
        manifest[rel] = file_sha256(path)
    return manifest


def workflow_set_sha256(contract: dict[str, Any]) -> str:
    return sha256_bytes(canonical(workflow_set_manifest(contract)))


def seal_config(value: dict[str, Any]) -> dict[str, Any]:
    base = {k: v for k, v in value.items() if k != 'configSha256'}
    base['configSha256'] = sha256_bytes(canonical(base))
    return base


def render_template(contract: dict[str, Any], contract_path: Path, repository: str) -> dict[str, Any]:
    validate_repository_name(repository)
    variables, secrets = required_names(contract)
    runner_names = {role['role']: f'__SET_RUNNER_NAME__:{role["role"]}' for role in contract['selfHostedRoles']}
    cfg = {
        'schemaVersion': 3,
        'revision': BOOTSTRAP_REVISION,
        'repository': repository,
        'contractSha256': file_sha256(contract_path),
        'repositoryBinding': None,
        'productionOperators': [],
        'environmentVariables': {
            env: {name: {'sourceEnv': source_env_name('VAR', env, name)} for name in sorted(names)}
            for env, names in sorted(variables.items()) if names
        },
        'environmentSecrets': {
            env: {name: {'sourceEnv': source_env_name('SECRET', env, name)} for name in sorted(names)}
            for env, names in sorted(secrets.items()) if names
        },
        'runnerNames': runner_names,
        'notes': [
            'This file contains source environment-variable names only, never secret values.',
            'Use set-runner for runner mappings and set-operator for authorized production operators; do not edit the sealed JSON manually.',
            'Run bind from the checked-out default branch before any live plan, runner registration, apply, or verify operation.',
            'New production environments are created default-branch-only; incompatible existing deployment branch policies fail closed instead of being silently rewritten.',
        ],
    }
    return seal_config(cfg)



def assert_source_integrity_clean() -> None:
    import importlib.util
    path = ROOT / 'scripts' / 'source_integrity.py'
    spec = importlib.util.spec_from_file_location('mte_source_integrity_for_onboarding', path)
    if spec is None or spec.loader is None:
        raise ProvisionError('could not load Source Integrity verifier')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    errors = module.verify_source_integrity(ROOT)
    if errors:
        raise ProvisionError('local source tree does not satisfy SOURCE_SHA256SUMS.txt: ' + '; '.join(errors[:5]))

def validate_binding(binding: dict[str, Any], cfg: dict[str, Any], contract: dict[str, Any], *, check_local: bool) -> None:
    if binding.get('fullName', '').lower() != str(cfg['repository']).lower():
        raise ProvisionError('repository binding fullName does not match bootstrap repository')
    if not isinstance(binding.get('repositoryId'), int) or int(binding['repositoryId']) <= 0:
        raise ProvisionError('repository binding repositoryId is invalid')
    branch = str(binding.get('defaultBranch', ''))
    if not branch or any(ch.isspace() for ch in branch):
        raise ProvisionError('repository binding defaultBranch is invalid')
    head = str(binding.get('defaultBranchHeadSha', '')).lower()
    if not SHA_RE.fullmatch(head):
        raise ProvisionError('repository binding defaultBranchHeadSha is invalid')
    resolved = binding.get('authorizedOperators')
    if not isinstance(resolved, list) or not resolved:
        raise ProvisionError('repository binding authorizedOperators is missing')
    resolved_logins = []
    ids = set()
    for item in resolved:
        if not isinstance(item, dict) or not GITHUB_LOGIN_RE.fullmatch(str(item.get('login', ''))) or not str(item.get('id', '')).isdigit():
            raise ProvisionError('repository binding authorizedOperators entry is invalid')
        resolved_logins.append(str(item['login']).lower())
        ids.add(str(item['id']))
    if len(ids) != len(resolved) or sorted(resolved_logins) != sorted(str(x).lower() for x in cfg.get('productionOperators') or []):
        raise ProvisionError('repository binding authorizedOperators does not match configured productionOperators')
    if binding.get('workflowSetSha256') != workflow_set_sha256(contract):
        raise ProvisionError('repository binding workflowSetSha256 does not match this source tree')
    if check_local:
        if not SOURCE_INTEGRITY.is_file() or binding.get('sourceIntegritySha256') != file_sha256(SOURCE_INTEGRITY):
            raise ProvisionError('repository binding sourceIntegritySha256 does not match this source tree')
        assert_source_integrity_clean()


def validate_config(
    cfg: dict[str, Any],
    contract: dict[str, Any],
    contract_path: Path,
    *,
    require_binding: bool = False,
    check_local_binding: bool = True,
) -> None:
    if cfg.get('schemaVersion') != 3 or cfg.get('revision') != BOOTSTRAP_REVISION:
        raise ProvisionError('unsupported production infrastructure bootstrap config')
    if cfg.get('contractSha256') != file_sha256(contract_path):
        raise ProvisionError('bootstrap config is bound to a different production execution contract')
    if cfg.get('configSha256') != seal_config(cfg)['configSha256']:
        raise ProvisionError('bootstrap configSha256 mismatch')
    repository = str(cfg.get('repository', ''))
    validate_repository_name(repository)
    operators = cfg.get('productionOperators')
    if not isinstance(operators, list) or len(operators) != len(set(str(x).lower() for x in operators)):
        raise ProvisionError('productionOperators must be a unique JSON list')
    for login in operators:
        if not isinstance(login, str) or not GITHUB_LOGIN_RE.fullmatch(login):
            raise ProvisionError(f'invalid production operator GitHub login: {login!r}')
    if require_binding and not operators:
        raise ProvisionError('at least one production operator must be configured before repository binding/live operations')
    variables, secrets = required_names(contract)
    var_cfg = cfg.get('environmentVariables') or {}
    sec_cfg = cfg.get('environmentSecrets') or {}
    for env, names in variables.items():
        for name in names:
            source = (((var_cfg.get(env) or {}).get(name) or {}).get('sourceEnv'))
            if not source:
                raise ProvisionError(f'missing variable source mapping: {env}:{name}')
    for env, names in secrets.items():
        for name in names:
            source = (((sec_cfg.get(env) or {}).get(name) or {}).get('sourceEnv'))
            if not source:
                raise ProvisionError(f'missing secret source mapping: {env}:{name}')
    runner_names = cfg.get('runnerNames') or {}
    for role in contract['selfHostedRoles']:
        runner = str(runner_names.get(role['role'], ''))
        if not runner:
            raise ProvisionError(f'missing runner name mapping: {role["role"]}')
        validate_runner_name(runner, role['role'])
    binding = cfg.get('repositoryBinding')
    if require_binding and not isinstance(binding, dict):
        raise ProvisionError('bootstrap config must be repository-bound before live mutation or verification')
    if isinstance(binding, dict):
        validate_binding(binding, cfg, contract, check_local=check_local_binding)



def set_runner_name(cfg: dict[str, Any], contract: dict[str, Any], role_name: str, runner_name: str) -> dict[str, Any]:
    if cfg.get('repositoryBinding') is not None:
        raise ProvisionError('runner mappings cannot be changed after repository binding; create a fresh template to reconfigure')
    role = next((x for x in contract['selfHostedRoles'] if x['role'] == role_name), None)
    if role is None:
        raise ProvisionError(f'unknown production runner role: {role_name}')
    validate_runner_name(runner_name, role_name)
    if runner_name.startswith('__SET_RUNNER_NAME__'):
        raise ProvisionError('set-runner requires a real runner name, not a placeholder')
    updated = dict(cfg)
    updated['runnerNames'] = dict(cfg.get('runnerNames') or {})
    updated['runnerNames'][role_name] = runner_name
    return seal_config(updated)

def set_operator(cfg: dict[str, Any], login: str) -> dict[str, Any]:
    if cfg.get('repositoryBinding') is not None:
        raise ProvisionError('production operators cannot be changed after repository binding; create a fresh template to reconfigure')
    if not GITHUB_LOGIN_RE.fullmatch(login):
        raise ProvisionError(f'invalid production operator GitHub login: {login!r}')
    updated = dict(cfg)
    values = {str(x).lower(): str(x) for x in (cfg.get('productionOperators') or [])}
    values[login.lower()] = login
    updated['productionOperators'] = [values[k] for k in sorted(values)]
    return seal_config(updated)


def operator_allowlist_json(cfg: dict[str, Any]) -> str:
    binding = cfg.get('repositoryBinding') or {}
    resolved = binding.get('authorizedOperators') or []
    ids = []
    for item in resolved:
        if not isinstance(item, dict) or not str(item.get('id', '')).isdigit():
            raise ProvisionError('repository binding is missing resolved production operator IDs')
        ids.append(str(item['id']))
    if not ids:
        raise ProvisionError('repository binding has no resolved production operator IDs')
    return json.dumps(sorted(set(ids), key=int), separators=(',', ':'))


def api_request(method: str, url: str, token: str, api_version: str, body: dict[str, Any] | None = None) -> dict[str, Any] | None:
    payload = None if body is None else json.dumps(body).encode('utf-8')
    req = urllib.request.Request(
        url,
        method=method,
        data=payload,
        headers={
            'Accept': 'application/vnd.github+json',
            'Authorization': f'Bearer {token}',
            'X-GitHub-Api-Version': api_version,
            'User-Agent': 'mte-production-infrastructure-provisioner',
            **({'Content-Type': 'application/json'} if body is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            return json.loads(raw.decode('utf-8')) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode('utf-8', errors='replace')[:500]
        raise ProvisionError(f'GitHub API {method} failed with HTTP {exc.code}: {raw}') from exc
    except urllib.error.URLError as exc:
        raise ProvisionError(f'GitHub API {method} failed: {exc.reason}') from exc


def repo_api_base(repository: str) -> str:
    owner, repo = repository.split('/', 1)
    return f'https://api.github.com/repos/{urllib.parse.quote(owner, safe="")}/{urllib.parse.quote(repo, safe="")}'


def live_repository_identity(repository: str, token: str, contract: dict[str, Any]) -> dict[str, Any]:
    api_version = contract['githubInfrastructureAudit']['apiVersion']
    base = repo_api_base(repository)
    repo = api_request('GET', base, token, api_version)
    if not isinstance(repo, dict):
        raise ProvisionError('GitHub repository metadata response is invalid')
    full_name = str(repo.get('full_name', ''))
    if full_name.lower() != repository.lower():
        raise ProvisionError(f'GitHub repository identity mismatch: expected {repository}, got {full_name or "<missing>"}')
    repository_id = repo.get('id')
    default_branch = str(repo.get('default_branch', ''))
    if not isinstance(repository_id, int) or not default_branch:
        raise ProvisionError('GitHub repository metadata is missing id/default_branch')
    branch = api_request('GET', f'{base}/commits/{urllib.parse.quote(default_branch, safe="")}', token, api_version)
    head = str((branch or {}).get('sha', '')).lower() if isinstance(branch, dict) else ''
    if not SHA_RE.fullmatch(head):
        raise ProvisionError('GitHub default branch head SHA is missing or invalid')
    return {
        'repositoryId': int(repository_id),
        'fullName': full_name,
        'defaultBranch': default_branch,
        'defaultBranchHeadSha': head,
    }


def normalize_origin_url(url: str) -> str | None:
    text = url.strip()
    if text.endswith('.git'):
        text = text[:-4]
    if text.startswith('git@github.com:'):
        return text[len('git@github.com:'):]
    for prefix in ('https://github.com/', 'ssh://git@github.com/'):
        if text.startswith(prefix):
            return text[len(prefix):]
    return None


def git_output(*args: str) -> str:
    proc = subprocess.run(['git', *args], cwd=ROOT, text=True, capture_output=True)
    if proc.returncode != 0:
        raise ProvisionError(f'git {" ".join(args)} failed; run repository binding from the checked-out project repository')
    return proc.stdout.strip()


def resolve_operator(login: str, token: str, contract: dict[str, Any]) -> dict[str, str]:
    api_version = contract['githubInfrastructureAudit']['apiVersion']
    user = api_request('GET', f'https://api.github.com/users/{urllib.parse.quote(login, safe="")}', token, api_version)
    if not isinstance(user, dict) or not isinstance(user.get('id'), int) or not user.get('login'):
        raise ProvisionError(f'could not resolve production operator GitHub identity: {login}')
    return {'login': str(user['login']), 'id': str(int(user['id']))}


def bind_config(cfg: dict[str, Any], contract: dict[str, Any], contract_path: Path, token: str) -> dict[str, Any]:
    if cfg.get('repositoryBinding') is not None:
        raise ProvisionError('bootstrap config is already repository-bound; create a fresh template to rebind')
    identity = live_repository_identity(cfg['repository'], token, contract)
    local_head = git_output('rev-parse', 'HEAD').lower()
    local_branch = git_output('branch', '--show-current')
    origin = normalize_origin_url(git_output('remote', 'get-url', 'origin'))
    if origin is None or origin.lower() != str(cfg['repository']).lower():
        raise ProvisionError(f'local origin does not match bootstrap repository: {origin or "<unsupported-origin>"}')
    if local_branch != identity['defaultBranch']:
        raise ProvisionError(f'bind must run from default branch {identity["defaultBranch"]}, not {local_branch or "<detached>"}')
    if local_head != identity['defaultBranchHeadSha']:
        raise ProvisionError('local HEAD does not equal the live GitHub default-branch head; push/sync before binding')
    bound = dict(cfg)
    resolved_operators = [resolve_operator(login, token, contract) for login in cfg.get('productionOperators') or []]
    if len({x['id'] for x in resolved_operators}) != len(resolved_operators):
        raise ProvisionError('productionOperators resolve to duplicate GitHub actor IDs')
    bound['repositoryBinding'] = {
        **identity,
        'workflowSetSha256': workflow_set_sha256(contract),
        'sourceIntegritySha256': file_sha256(SOURCE_INTEGRITY),
        'authorizedOperators': sorted(resolved_operators, key=lambda x: int(x['id'])),
    }
    bound = seal_config(bound)
    validate_config(bound, contract, contract_path, require_binding=True)
    return bound


def verify_live_binding(cfg: dict[str, Any], contract: dict[str, Any], token: str) -> dict[str, Any]:
    binding = cfg.get('repositoryBinding') or {}
    live = live_repository_identity(cfg['repository'], token, contract)
    checks = {
        'repositoryId': int(live['repositoryId']) == int(binding.get('repositoryId', -1)),
        'fullName': str(live['fullName']).lower() == str(binding.get('fullName', '')).lower(),
        'defaultBranch': live['defaultBranch'] == binding.get('defaultBranch'),
        'defaultBranchHeadSha': live['defaultBranchHeadSha'] == binding.get('defaultBranchHeadSha'),
        'workflowSetSha256': binding.get('workflowSetSha256') == workflow_set_sha256(contract),
        'sourceIntegritySha256': binding.get('sourceIntegritySha256') == file_sha256(SOURCE_INTEGRITY),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ProvisionError('repository binding drift detected: ' + ', '.join(failed))
    return {'passed': True, 'checks': checks, 'repositoryId': live['repositoryId'], 'defaultBranchHeadSha': live['defaultBranchHeadSha']}


def collect_audit_snapshot(repository: str, token: str, contract: dict[str, Any]) -> dict[str, Any]:
    import importlib.util
    path = ROOT / 'scripts' / 'audit_github_production_infrastructure.py'
    spec = importlib.util.spec_from_file_location('mte_github_infra_audit', path)
    if spec is None or spec.loader is None:
        raise ProvisionError('could not load GitHub infrastructure audit module')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.collect_live_snapshot(repository, token, contract)


def custom_labels(role: dict[str, Any]) -> list[str]:
    builtins = {'self-hosted', 'linux', 'windows', 'macos', 'x64', 'arm64', 'arm', 'x86'}
    return [str(label) for label in role['labels'] if str(label).lower() not in builtins]


def branch_policy_state(env: dict[str, Any], default_branch: str) -> str:
    deployment = env.get('deploymentBranchPolicy')
    policies = env.get('deploymentBranchPolicies') or []
    if isinstance(deployment, dict) and deployment.get('protected_branches') is False and deployment.get('custom_branch_policies') is True:
        if len(policies) == 0:
            return 'custom-empty'
        if len(policies) == 1 and str(policies[0].get('name', '')) == default_branch and policies[0].get('type') in (None, '', 'branch'):
            return 'default-only'
        return 'custom-incompatible'
    return 'incompatible'


def create_default_branch_policy(base: str, environment: str, default_branch: str, token: str, api_version: str) -> None:
    encoded = urllib.parse.quote(environment, safe='')
    api_request(
        'POST',
        f'{base}/environments/{encoded}/deployment-branch-policies',
        token,
        api_version,
        {'name': default_branch, 'type': 'branch'},
    )


def build_plan(cfg: dict[str, Any], contract: dict[str, Any], snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    envs = (snapshot or {}).get('environments') or {}
    runners = (snapshot or {}).get('runners') or []
    default_branch = str((snapshot or {}).get('defaultBranch') or (cfg.get('repositoryBinding') or {}).get('defaultBranch') or '')
    actions: list[dict[str, Any]] = []
    missing_sources: list[dict[str, str]] = []
    blocking_policies: list[dict[str, str]] = []
    trust = contract['workflowTrust']
    variable_name = str(trust['operatorAllowlistVariable'])
    expected_operators = operator_allowlist_json(cfg) if isinstance(cfg.get('repositoryBinding'), dict) else None
    repository_variables = (snapshot or {}).get('repositoryVariables') or {}
    current_operators = repository_variables.get(variable_name) if snapshot is not None else None
    actions.append({
        'type': 'repository-variable-set',
        'name': variable_name,
        'value': expected_operators,
        'needed': (current_operators != expected_operators) if snapshot is not None and expected_operators is not None else None,
        'operatorCount': len(cfg.get('productionOperators') or []),
    })
    for env in sorted(contract['protectedEnvironments']):
        present = env in envs if snapshot is not None else None
        actions.append({'type': 'environment-create-if-missing', 'environment': env, 'needed': (not present) if present is not None else None})
        if snapshot is not None and present:
            state = branch_policy_state(envs[env], default_branch)
            action = {'type': 'environment-default-branch-policy', 'environment': env, 'state': state, 'expectedBranch': default_branch}
            if state == 'default-only':
                action['needed'] = False
            elif state == 'custom-empty':
                action['needed'] = True
                action['safeAdditive'] = True
            else:
                action['needed'] = True
                action['blocking'] = True
                blocking_policies.append({'environment': env, 'state': state})
            actions.append(action)
        elif snapshot is not None:
            actions.append({'type': 'environment-default-branch-policy', 'environment': env, 'state': 'created-with-default-only', 'expectedBranch': default_branch, 'needed': True, 'safeAdditive': True})
    for env, names in sorted((cfg.get('environmentVariables') or {}).items()):
        for name, src in sorted(names.items()):
            source = str(src['sourceEnv'])
            present = bool(os.environ.get(source, ''))
            actions.append({'type': 'environment-variable-set', 'environment': env, 'name': name, 'sourceEnv': source, 'sourcePresent': present})
            if not present:
                missing_sources.append({'type': 'variable', 'environment': env, 'name': name, 'sourceEnv': source})
    for env, names in sorted((cfg.get('environmentSecrets') or {}).items()):
        for name, src in sorted(names.items()):
            source = str(src['sourceEnv'])
            present = bool(os.environ.get(source, ''))
            actions.append({'type': 'environment-secret-set', 'environment': env, 'name': name, 'sourceEnv': source, 'sourcePresent': present, 'sensitive': True})
            if not present:
                missing_sources.append({'type': 'secret', 'environment': env, 'name': name, 'sourceEnv': source})
    for role in contract['selfHostedRoles']:
        runner_name = str(cfg['runnerNames'][role['role']])
        match = next((r for r in runners if str(r.get('name')) == runner_name), None) if snapshot is not None else None
        actions.append({
            'type': 'runner-label-add',
            'role': role['role'],
            'runnerName': runner_name,
            'customLabels': custom_labels(role),
            'runnerPresent': match is not None if snapshot is not None else None,
            'runnerId': match.get('id') if match else None,
        })
    return {
        'schemaVersion': 3,
        'revision': BOOTSTRAP_REVISION,
        'repository': cfg['repository'],
        'repositoryId': (cfg.get('repositoryBinding') or {}).get('repositoryId'),
        'defaultBranchHeadSha': (cfg.get('repositoryBinding') or {}).get('defaultBranchHeadSha'),
        'contractRevision': contract['revision'],
        'configSha256': cfg['configSha256'],
        'actions': actions,
        'missingSourceCount': len(missing_sources),
        'missingSources': missing_sources,
        'blockingPolicyCount': len(blocking_policies),
        'blockingPolicies': blocking_policies,
        'notice': 'Plan never contains variable/secret values. New environments are default-branch-only; incompatible existing deployment branch policies block apply instead of being silently rewritten.',
    }


def require_gh() -> str:
    path = shutil.which('gh')
    if not path:
        raise ProvisionError('GitHub CLI (gh) is required to materialize environment variables/secrets safely')
    return path


def gh_set(kind: str, repository: str, environment: str, name: str, value: str, token: str) -> None:
    gh = require_gh()
    command = [gh, kind, 'set', name, '--env', environment, '--repo', repository]
    proc = subprocess.run(command, input=value, text=True, capture_output=True, env={**os.environ, 'GH_TOKEN': token})
    if proc.returncode != 0:
        stderr = proc.stderr.strip()[:500]
        raise ProvisionError(f'gh {kind} set failed for {environment}:{name}: {stderr}')


def apply(cfg: dict[str, Any], contract: dict[str, Any], token: str) -> dict[str, Any]:
    binding_report = verify_live_binding(cfg, contract, token)
    repository = cfg['repository']
    api_version = contract['githubInfrastructureAudit']['apiVersion']
    base = repo_api_base(repository)
    snapshot = collect_audit_snapshot(repository, token, contract)
    envs = snapshot.get('environments') or {}
    default_branch = str(snapshot.get('defaultBranch') or (cfg.get('repositoryBinding') or {}).get('defaultBranch') or '')
    if not default_branch:
        raise ProvisionError('live GitHub snapshot is missing defaultBranch')
    incompatible = []
    for env in sorted(contract['protectedEnvironments']):
        if env not in envs:
            continue
        state = branch_policy_state(envs[env], default_branch)
        if state not in {'default-only', 'custom-empty'}:
            incompatible.append(f'{env}:{state}')
    if incompatible:
        raise ProvisionError('existing production environment deployment branch policy is not safely default-branch-only: ' + ', '.join(incompatible) + '; configure custom branch policies manually before apply')

    results: list[dict[str, Any]] = []
    variable_name = str(contract['workflowTrust']['operatorAllowlistVariable'])
    operator_value = operator_allowlist_json(cfg)
    existing_repo_variables = snapshot.get('repositoryVariables') or {}
    if variable_name in existing_repo_variables:
        api_request('PATCH', f'{base}/actions/variables/{urllib.parse.quote(variable_name, safe="")}', token, api_version, {'name': variable_name, 'value': operator_value})
        operator_action = 'updated'
    else:
        api_request('POST', f'{base}/actions/variables', token, api_version, {'name': variable_name, 'value': operator_value})
        operator_action = 'created'
    results.append({'type': 'repository-variable', 'name': variable_name, 'action': operator_action, 'operatorCount': len(cfg.get('productionOperators') or [])})
    for env in sorted(contract['protectedEnvironments']):
        encoded = urllib.parse.quote(env, safe='')
        if env not in envs:
            api_request(
                'PUT',
                f'{base}/environments/{encoded}',
                token,
                api_version,
                {'deployment_branch_policy': {'protected_branches': False, 'custom_branch_policies': True}},
            )
            create_default_branch_policy(base, env, default_branch, token, api_version)
            results.append({'type': 'environment', 'environment': env, 'action': 'created-default-branch-only', 'branch': default_branch})
            continue
        state = branch_policy_state(envs[env], default_branch)
        if state == 'custom-empty':
            create_default_branch_policy(base, env, default_branch, token, api_version)
            results.append({'type': 'environment', 'environment': env, 'action': 'added-default-branch-policy', 'branch': default_branch})
        else:
            results.append({'type': 'environment', 'environment': env, 'action': 'preserved-default-branch-only', 'branch': default_branch})
    for env, names in sorted((cfg.get('environmentVariables') or {}).items()):
        for name, src in sorted(names.items()):
            source = src['sourceEnv']
            value = os.environ.get(source, '')
            if not value:
                raise ProvisionError(f'missing local source environment variable: {source}')
            gh_set('variable', repository, env, name, value, token)
            results.append({'type': 'environment-variable', 'environment': env, 'name': name, 'action': 'set', 'sourceEnv': source})
    for env, names in sorted((cfg.get('environmentSecrets') or {}).items()):
        for name, src in sorted(names.items()):
            source = src['sourceEnv']
            value = os.environ.get(source, '')
            if not value:
                raise ProvisionError(f'missing local secret source environment variable: {source}')
            gh_set('secret', repository, env, name, value, token)
            results.append({'type': 'environment-secret', 'environment': env, 'name': name, 'action': 'set', 'sourceEnv': source, 'sensitive': True})
    snapshot = collect_audit_snapshot(repository, token, contract)
    runners = snapshot.get('runners') or []
    for role in contract['selfHostedRoles']:
        runner_name = str(cfg['runnerNames'][role['role']])
        runner = next((r for r in runners if str(r.get('name')) == runner_name), None)
        if runner is None:
            raise ProvisionError(f'runner is not registered yet: {runner_name}; use the runner-command subcommand on that host first')
        labels = custom_labels(role)
        if labels:
            api_request('POST', f'{base}/actions/runners/{int(runner["id"])}/labels', token, api_version, {'labels': labels})
        results.append({'type': 'runner-labels', 'role': role['role'], 'runnerName': runner_name, 'action': 'added', 'labels': labels})
    return {
        'passed': True,
        'repository': repository,
        'repositoryBinding': binding_report,
        'results': results,
        'notice': 'Existing reviewer/wait protection rules are preserved. Production environments must be exact-default-branch-only; incompatible existing branch policies fail closed. No secret values are included in this report.',
    }


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def runner_command(cfg: dict[str, Any], contract: dict[str, Any], role_name: str) -> dict[str, Any]:
    role = next((x for x in contract['selfHostedRoles'] if x['role'] == role_name), None)
    if role is None:
        raise ProvisionError(f'unknown production runner role: {role_name}')
    runner_name = str(cfg['runnerNames'][role_name])
    if runner_name.startswith('__SET_RUNNER_NAME__'):
        raise ProvisionError(f'replace the runnerNames placeholder for {role_name} before generating registration commands')
    validate_runner_name(runner_name, role_name)
    labels = ','.join(custom_labels(role))
    repository = str(cfg['repository'])
    validate_repository_name(repository)
    api_path = f'repos/{repository}/actions/runners/registration-token'
    repo_meta_path = f'repos/{repository}'
    branch_path = f'repos/{repository}/commits/{cfg["repositoryBinding"]["defaultBranch"]}'
    expected_id = str(cfg['repositoryBinding']['repositoryId'])
    expected_head = str(cfg['repositoryBinding']['defaultBranchHeadSha'])
    repo_url = f'https://github.com/{repository}'
    if role['os'] == 'Windows':
        command = (
            f'$liveId = gh api {ps_quote(repo_meta_path)} --jq .id; '
            f'$liveHead = gh api {ps_quote(branch_path)} --jq .sha; '
            f'if ($liveId -ne {ps_quote(expected_id)} -or $liveHead -ne {ps_quote(expected_head)}) {{ throw {ps_quote("Repository onboarding binding drift; abort runner registration")} }}; '
            f'$token = gh api --method POST {ps_quote(api_path)} --jq .token; '
            f'.\\config.cmd --url {ps_quote(repo_url)} --token $token --name {ps_quote(runner_name)} '
            f'--labels {ps_quote(labels)} --unattended; Remove-Variable token,liveId,liveHead'
        )
        shell = 'powershell'
    else:
        command = (
            f'LIVE_ID="$(gh api {shlex.quote(repo_meta_path)} --jq .id)"; '
            f'LIVE_HEAD="$(gh api {shlex.quote(branch_path)} --jq .sha)"; '
            f'[ "$LIVE_ID" = {shlex.quote(expected_id)} ] && [ "$LIVE_HEAD" = {shlex.quote(expected_head)} ] || {{ echo {shlex.quote("Repository onboarding binding drift; abort runner registration")} >&2; exit 2; }}; '
            f'TOKEN="$(gh api --method POST {shlex.quote(api_path)} --jq .token)"; '
            f'./config.sh --url {shlex.quote(repo_url)} --token "$TOKEN" --name {shlex.quote(runner_name)} '
            f'--labels {shlex.quote(labels)} --unattended; unset TOKEN LIVE_ID LIVE_HEAD'
        )
        shell = 'bash'
    return {
        'passed': True,
        'role': role_name,
        'runnerName': runner_name,
        'shell': shell,
        'command': command,
        'repositoryId': (cfg.get('repositoryBinding') or {}).get('repositoryId'),
        'boundSourceHeadSha': (cfg.get('repositoryBinding') or {}).get('defaultBranchHeadSha'),
        'notice': 'Run this from an unpacked GitHub Actions runner directory on the target host. The short-lived registration token is held only in memory.',
    }


def verify(repository: str, contract: dict[str, Any], token: str, cfg: dict[str, Any]) -> dict[str, Any]:
    import importlib.util
    binding_report = verify_live_binding(cfg, contract, token)
    path = ROOT / 'scripts' / 'audit_github_production_infrastructure.py'
    spec = importlib.util.spec_from_file_location('mte_github_infra_audit_verify', path)
    if spec is None or spec.loader is None:
        raise ProvisionError('could not load GitHub infrastructure audit module')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    snapshot = module.collect_live_snapshot(repository, token, contract)
    checks = module.audit_snapshot(snapshot, contract)
    variable_name = str(contract['workflowTrust']['operatorAllowlistVariable'])
    expected_operator_value = operator_allowlist_json(cfg)
    actual_operator_value = (snapshot.get('repositoryVariables') or {}).get(variable_name)
    checks.append({
        'name': f'repository-variable:{variable_name}:matches-onboarding',
        'passed': actual_operator_value == expected_operator_value,
        'severity': 'error',
        'expectedOperatorCount': len(cfg.get('productionOperators') or []),
    })
    failures = [x for x in checks if x.get('severity') == 'error' and not x.get('passed')]
    warnings = [x for x in checks if x.get('severity') == 'warning' and not x.get('passed')]
    return {
        'passed': not failures,
        'repository': repository,
        'repositoryBinding': binding_report,
        'blockingFailureCount': len(failures),
        'warningCount': len(warnings),
        'checks': checks,
        'notice': 'Verification reads secret names only, never secret values.',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Fail-closed bootstrap for repository-side V1 production environments, variables, secret names and runner labels.')
    parser.add_argument('--contract', type=Path, default=DEFAULT_CONTRACT)
    sub = parser.add_subparsers(dest='command', required=True)

    p = sub.add_parser('template')
    p.add_argument('--repository', required=True)
    p.add_argument('--output', type=Path, required=True)

    p = sub.add_parser('set-runner')
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--role', required=True)
    p.add_argument('--name', required=True)

    p = sub.add_parser('set-operator')
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--login', required=True)

    p = sub.add_parser('bind')
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--token-env', default='MTE_INFRA_PROVISION_TOKEN')

    p = sub.add_parser('plan')
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--live', action='store_true')
    p.add_argument('--token-env', default='MTE_INFRA_PROVISION_TOKEN')

    p = sub.add_parser('apply')
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--token-env', default='MTE_INFRA_PROVISION_TOKEN')

    p = sub.add_parser('verify')
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--token-env', default='MTE_INFRA_PROVISION_TOKEN')

    p = sub.add_parser('runner-command')
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--role', required=True)

    args = parser.parse_args()
    contract_path = args.contract.resolve()
    contract = load_contract(contract_path)

    if args.command == 'template':
        cfg = render_template(contract, contract_path, args.repository)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(cfg, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'passed': True, 'output': str(args.output), 'configSha256': cfg['configSha256'], 'repositoryBound': False}, indent=2))
        return 0

    cfg = json.loads(args.config.read_text(encoding='utf-8'))
    require_binding = args.command in {'runner-command', 'apply', 'verify'} or (args.command == 'plan' and args.live)
    validate_config(cfg, contract, contract_path, require_binding=require_binding)

    if args.command == 'set-runner':
        updated = set_runner_name(cfg, contract, args.role, args.name)
        args.config.write_text(json.dumps(updated, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'passed': True, 'role': args.role, 'runnerName': args.name, 'configSha256': updated['configSha256']}, indent=2))
        return 0

    if args.command == 'set-operator':
        updated = set_operator(cfg, args.login)
        args.config.write_text(json.dumps(updated, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'passed': True, 'operator': args.login, 'operatorCount': len(updated['productionOperators']), 'configSha256': updated['configSha256']}, indent=2))
        return 0

    if args.command == 'bind':
        token = os.environ.get(args.token_env, '').strip()
        if not token:
            raise ProvisionError(f'{args.token_env} is required for bind')
        bound = bind_config(cfg, contract, contract_path, token)
        args.config.write_text(json.dumps(bound, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({
            'passed': True,
            'config': str(args.config),
            'repositoryId': bound['repositoryBinding']['repositoryId'],
            'defaultBranch': bound['repositoryBinding']['defaultBranch'],
            'defaultBranchHeadSha': bound['repositoryBinding']['defaultBranchHeadSha'],
            'workflowSetSha256': bound['repositoryBinding']['workflowSetSha256'],
            'configSha256': bound['configSha256'],
        }, indent=2))
        return 0

    if args.command == 'runner-command':
        print(json.dumps(runner_command(cfg, contract, args.role), indent=2))
        return 0

    token = os.environ.get(args.token_env, '').strip()
    if args.command == 'plan':
        snapshot = None
        if args.live:
            if not token:
                raise ProvisionError(f'{args.token_env} is required for --live planning')
            verify_live_binding(cfg, contract, token)
            snapshot = collect_audit_snapshot(cfg['repository'], token, contract)
        report = build_plan(cfg, contract, snapshot)
        print(json.dumps(report, indent=2))
        return 0 if report['missingSourceCount'] == 0 and report.get('blockingPolicyCount', 0) == 0 else 2

    if not token:
        raise ProvisionError(f'{args.token_env} is required for {args.command}')
    if args.command == 'apply':
        print(json.dumps(apply(cfg, contract, token), indent=2))
        return 0
    if args.command == 'verify':
        report = verify(cfg['repository'], contract, token, cfg)
        print(json.dumps(report, indent=2))
        return 0 if report['passed'] else 2
    raise ProvisionError('unsupported command')


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except ProvisionError as exc:
        print(json.dumps({'passed': False, 'error': str(exc)}, indent=2))
        raise SystemExit(2)
