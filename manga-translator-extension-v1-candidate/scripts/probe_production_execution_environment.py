from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / 'release-control' / 'production-execution-contract.json'


class ReadinessError(ValueError):
    pass


def load_contract(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('schemaVersion') != 4 or value.get('revision') != 'rev34-recovery-rotation-offsite-durability-v1':
        raise ReadinessError('production execution contract schema/revision is unsupported')
    return value


def command_output(command: list[str]) -> str | None:
    try:
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or result.stderr).strip()


def normalize_version(raw: str | None) -> str | None:
    if raw is None:
        return None
    match = re.search(r'(\d+\.\d+\.\d+)', raw)
    return match.group(1) if match else raw.strip()


def static_contract_checks(contract: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    toolchain = json.loads((ROOT / 'release-control' / 'toolchain.json').read_text(encoding='utf-8'))
    expected = contract['toolchain']
    actual = {
        'node': toolchain['canonicalExtensionBuild']['node'],
        'npm': toolchain['canonicalExtensionBuild']['npm'],
        'python': toolchain['canonicalEngineBuild']['python'],
        'uv': toolchain['canonicalEngineBuild']['uv'],
    }
    checks.append({'name': 'toolchain-contract-match', 'passed': actual == expected, 'expected': expected, 'actual': actual})

    for role in contract['selfHostedRoles']:
        body = (ROOT / role['workflow']).read_text(encoding='utf-8')
        labels = role['labels']
        label_expr = 'runs-on: [' + ', '.join(labels) + ']'
        checks.append({'name': f"workflow-labels:{role['role']}", 'passed': label_expr in body, 'expected': label_expr})
        checks.append({'name': f"workflow-environment:{role['role']}", 'passed': role['environment'] in body, 'expected': role['environment']})
        for name in role.get('requiredVariables', []):
            checks.append({'name': f"workflow-variable:{role['role']}:{name}", 'passed': f'vars.{name}' in body, 'expected': name})
        for name in role.get('requiredSecrets', []):
            checks.append({'name': f"workflow-secret:{role['role']}:{name}", 'passed': f'secrets.{name}' in body, 'expected': name})

    mac = contract['publicSigning']['macos']
    mac_body = (ROOT / mac['workflow']).read_text(encoding='utf-8')
    for name in mac['requiredSecrets']:
        checks.append({'name': f'macos-signing-secret:{name}', 'passed': f'secrets.{name}' in mac_body, 'expected': name})
    checks.append({'name': 'macos-ephemeral-keychain', 'passed': 'security create-keychain' in mac_body and 'MTE_NOTARY_KEY_P8_BASE64' in mac_body})
    checks.append({'name': 'macos-no-preexisting-notary-profile', 'passed': 'secrets.MTE_NOTARY_PROFILE' not in mac_body})

    readiness_body = (ROOT / '.github' / 'workflows' / 'production-execution-readiness.yml').read_text(encoding='utf-8')
    audit_cfg = contract['githubInfrastructureAudit']
    checks.append({'name': 'github-infrastructure-audit-wired', 'passed': 'audit_github_production_infrastructure.py' in readiness_body})
    checks.append({'name': 'github-infrastructure-audit-token-wired', 'passed': f"secrets.{audit_cfg['repositoryAuditSecret']}" in readiness_body, 'expected': audit_cfg['repositoryAuditSecret']})
    checks.append({'name': 'github-infrastructure-pagination-required', 'passed': audit_cfg.get('paginationRequired') is True})
    checks.append({'name': 'github-infrastructure-token-actions-read', 'passed': 'Actions:read' in audit_cfg.get('requiredTokenPermissions', [])})
    checks.append({'name': 'github-infrastructure-audit-environment-wired', 'passed': f"environment: {audit_cfg.get('repositoryAuditEnvironment')}" in readiness_body, 'expected': audit_cfg.get('repositoryAuditEnvironment')})
    checks.append({'name': 'github-infrastructure-default-branch-only-required', 'passed': audit_cfg.get('requireDefaultBranchOnlyEnvironments') is True and all(v.get('requiredDeploymentBranchPolicy') == 'default-branch-only' for v in contract.get('protectedEnvironments', {}).values())})
    promotion_body = (ROOT / '.github' / 'workflows' / 'promote-production-qualification.yml').read_text(encoding='utf-8')
    checks.append({'name': 'qualification-promotion-environment-audited', 'passed': 'production-qualification-promotion' in contract.get('protectedEnvironments', {}) and 'environment: production-qualification-promotion' in promotion_body})

    win = contract['publicSigning']['windows']
    win_body = (ROOT / win['workflow']).read_text(encoding='utf-8')
    checks.append({'name': 'windows-artifact-signing-action', 'passed': win['action'] in win_body, 'expected': win['action']})
    checks.append({'name': 'windows-no-local-signing-path-secrets', 'passed': all(x not in win_body for x in ('MTE_SIGNTOOL', 'MTE_ARTIFACT_SIGNING_DLIB', 'MTE_ARTIFACT_SIGNING_METADATA'))})
    for name in win['requiredSecrets']:
        checks.append({'name': f'windows-signing-secret:{name}', 'passed': f'secrets.{name}' in win_body, 'expected': name})
    for name in win['requiredVariables']:
        checks.append({'name': f'windows-signing-variable:{name}', 'passed': f'vars.{name}' in win_body, 'expected': name})

    return checks


def live_role_checks(contract: dict[str, Any], role_name: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    roles = {item['role']: item for item in contract['selfHostedRoles']}
    if role_name not in roles:
        raise ReadinessError(f'unknown self-hosted role: {role_name}')
    role = roles[role_name]
    checks: list[dict[str, Any]] = []

    observed_os = platform.system()
    observed_arch = platform.machine().lower()
    checks.append({'name': 'os', 'passed': observed_os == role['os'], 'expected': role['os'], 'actual': observed_os})
    checks.append({'name': 'architecture', 'passed': observed_arch in [x.lower() for x in role['architectures']], 'expected': role['architectures'], 'actual': observed_arch})

    for name in role.get('requiredVariables', []):
        present = bool(os.environ.get(name, '').strip())
        checks.append({'name': f'env:{name}', 'passed': present, 'sensitive': False})
    for name in role.get('requiredSecrets', []):
        present = bool(os.environ.get(name, '').strip())
        checks.append({'name': f'secret:{name}', 'passed': present, 'sensitive': True})
    for name in role.get('requiredDirectoryVariables', []):
        raw = os.environ.get(name, '').strip()
        checks.append({'name': f'directory:{name}', 'passed': bool(raw) and Path(raw).is_dir(), 'actual': 'configured-directory' if raw and Path(raw).is_dir() else 'missing-or-not-directory'})

    versions = contract['toolchain']
    commands = {
        'node': ['node', '--version'],
        'npm': ['npm', '--version'],
        'python': [sys.executable, '--version'],
        'uv': ['uv', '--version'],
    }
    for tool in role.get('toolchainChecks', []):
        raw = command_output(commands[tool])
        actual = normalize_version(raw)
        checks.append({'name': f'toolchain:{tool}', 'passed': actual == versions[tool], 'expected': versions[tool], 'actual': actual})

    disk = shutil.disk_usage(ROOT)
    observation = {
        'os': observed_os,
        'architecture': observed_arch,
        'freeDiskBytes': disk.free,
        'pythonExecutable': str(Path(sys.executable).resolve()),
    }
    return observation, checks


def main() -> int:
    parser = argparse.ArgumentParser(description='Fail-closed production execution infrastructure readiness probe.')
    parser.add_argument('--contract', type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument('--role', help='Live self-hosted role to probe. Omit for static contract verification only.')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--strict', action='store_true')
    args = parser.parse_args()

    contract = load_contract(args.contract.resolve())
    checks = static_contract_checks(contract)
    observation: dict[str, Any] | None = None
    if args.role:
        observation, live = live_role_checks(contract, args.role)
        checks.extend(live)
    passed = all(bool(item.get('passed')) for item in checks)
    report = {
        'schemaVersion': 1,
        'revision': contract['revision'],
        'role': args.role or 'static',
        'passed': passed,
        'observation': observation,
        'checks': checks,
    }
    payload = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding='utf-8')
    print(payload, end='')
    if args.strict and not passed:
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
