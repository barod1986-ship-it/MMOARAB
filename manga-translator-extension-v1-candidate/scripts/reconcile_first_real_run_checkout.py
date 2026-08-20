from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / 'release-control' / 'production-execution-contract.json'
REVISION = 'rev31-post-merge-checkout-reconciliation-v1'
SHA40 = re.compile(r'^[0-9a-f]{40}$')
OPERATIONAL_UNTRACKED_PREFIXES = ('release/',)
OPERATIONAL_UNTRACKED_FILES = {'.mte-production-bootstrap.json', 'first-real-run-ledger.json'}


class ReconcileError(ValueError):
    pass


def run_git(repo_root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(['git', *args], cwd=repo_root, text=True, capture_output=True)
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()[:800]
        raise ReconcileError(f'git {" ".join(args)} failed: {detail}')
    return proc


def git_out(repo_root: Path, *args: str) -> str:
    return run_git(repo_root, *args).stdout.strip()


def normalize_repo_from_origin(url: str) -> str:
    value = url.strip()
    if value.startswith('git@github.com:'):
        path = value[len('git@github.com:'):]
    elif value.startswith('ssh://git@github.com/'):
        path = value[len('ssh://git@github.com/'):]
    else:
        parsed = urllib.parse.urlparse(value)
        if parsed.hostname not in {'github.com', 'www.github.com'}:
            raise ReconcileError('origin must point to github.com for production reconciliation')
        path = parsed.path.lstrip('/')
    if path.endswith('.git'):
        path = path[:-4]
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', path):
        raise ReconcileError('origin does not identify one canonical OWNER/REPO')
    return path


def status_entries(repo_root: Path) -> list[dict[str, str]]:
    proc = run_git(repo_root, 'status', '--porcelain=v1', '-z', '--untracked-files=all')
    raw = proc.stdout
    parts = raw.split('\0')
    out: list[dict[str, str]] = []
    i = 0
    while i < len(parts):
        item = parts[i]
        i += 1
        if not item:
            continue
        if len(item) < 4:
            raise ReconcileError('unexpected git status record')
        xy, path = item[:2], item[3:]
        if 'R' in xy or 'C' in xy:
            if i >= len(parts):
                raise ReconcileError('truncated rename/copy status record')
            other = parts[i]
            i += 1
            raise ReconcileError(f'renamed/copied paths are not allowed during checkout reconciliation: {path} -> {other}')
        out.append({'xy': xy, 'path': path})
    return out


def operational_untracked(path: str) -> bool:
    return path in OPERATIONAL_UNTRACKED_FILES or any(path.startswith(prefix) for prefix in OPERATIONAL_UNTRACKED_PREFIXES)


def target_bytes(repo_root: Path, target_sha: str, rel: str) -> bytes:
    proc = subprocess.run(['git', 'show', f'{target_sha}:{rel}'], cwd=repo_root, capture_output=True)
    if proc.returncode != 0:
        raise ReconcileError(f'target commit does not contain expected transition path {rel}')
    return proc.stdout


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_local_expected_bytes(repo_root: Path, target_sha: str, rel: str) -> None:
    path = repo_root / rel
    if path.is_symlink():
        raise ReconcileError(f'expected transition path is a symlink locally: {rel}')
    if not path.exists():
        return
    if not path.is_file():
        raise ReconcileError(f'expected transition path is not a regular file locally: {rel}')
    local = path.read_bytes()
    target = target_bytes(repo_root, target_sha, rel)
    if local != target:
        raise ReconcileError(f'local transition path differs from the reviewed merge commit bytes: {rel}')


def verify_source_integrity_default(repo_root: Path) -> None:
    script = repo_root / 'scripts' / 'verify_source_integrity.py'
    if not script.is_file():
        raise ReconcileError('verify_source_integrity.py is missing from the checkout')
    proc = subprocess.run([sys.executable, os.fspath(script)], cwd=repo_root, text=True, capture_output=True)
    if proc.returncode != 0:
        detail = (proc.stdout + proc.stderr).strip()[:1000]
        raise ReconcileError(f'post-reconciliation Source Integrity failed: {detail}')


def local_context(repo_root: Path, ledger: dict[str, Any]) -> dict[str, str]:
    if git_out(repo_root, 'rev-parse', '--is-inside-work-tree') != 'true':
        raise ReconcileError('local path is not a Git working tree')
    branch = git_out(repo_root, 'branch', '--show-current')
    if branch != str(ledger['defaultBranch']):
        raise ReconcileError(f'local checkout branch is {branch or "detached"}, expected default branch {ledger["defaultBranch"]}')
    origin = normalize_repo_from_origin(git_out(repo_root, 'remote', 'get-url', 'origin'))
    if origin.lower() != str(ledger['repository']).lower():
        raise ReconcileError(f'origin repository {origin} differs from sealed ledger repository {ledger["repository"]}')
    head = git_out(repo_root, 'rev-parse', 'HEAD').lower()
    if not SHA40.fullmatch(head):
        raise ReconcileError('local HEAD is not a valid commit SHA')
    return {'branch': branch, 'originRepository': origin, 'headSha': head}


def live_repo_snapshot(ledger: dict[str, Any], token: str, api_version: str) -> dict[str, str]:
    owner, repo = str(ledger['repository']).split('/', 1)
    base = f'https://api.github.com/repos/{urllib.parse.quote(owner, safe="")}/{urllib.parse.quote(repo, safe="")}'
    headers = {
        'Accept': 'application/vnd.github+json',
        'Authorization': f'Bearer {token}',
        'X-GitHub-Api-Version': api_version,
        'User-Agent': 'mte-post-merge-checkout-reconciliation',
    }
    def get(url: str) -> Any:
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace')[:500]
            raise ReconcileError(f'GitHub API GET failed with HTTP {exc.code}: {body}') from exc
        except urllib.error.URLError as exc:
            raise ReconcileError(f'GitHub API GET failed: {exc.reason}') from exc
    meta = get(base)
    if str(meta.get('id', '')) != str(ledger['repositoryId']):
        raise ReconcileError('live repository id differs from the sealed ledger identity')
    if str(meta.get('default_branch', '')) != str(ledger['defaultBranch']):
        raise ReconcileError('live default branch differs from the sealed ledger')
    branch = urllib.parse.quote(str(ledger['defaultBranch']), safe='')
    obj = get(f'{base}/branches/{branch}')
    sha = str(((obj or {}).get('commit') or {}).get('sha', '')).lower()
    if sha != str(ledger['currentSourceHeadSha']).lower():
        raise ReconcileError(f'live default branch HEAD {sha or "missing"} differs from ledger cursor {ledger["currentSourceHeadSha"]}')
    return {'repositoryId': str(meta.get('id')), 'defaultBranch': str(meta.get('default_branch')), 'headSha': sha}


def reconcile_checkout(
    *,
    repo_root: Path,
    ledger: dict[str, Any],
    merge_record: dict[str, Any],
    verify_source_integrity: Callable[[Path], None] = verify_source_integrity_default,
    fetch: bool = True,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    ctx = local_context(repo_root, ledger)
    target = str(ledger['currentSourceHeadSha']).lower()
    before = str(merge_record.get('sourceHeadShaBefore', '')).lower()
    after = str(merge_record.get('sourceHeadShaAfter', '')).lower()
    pr = merge_record.get('pullRequest') if isinstance(merge_record.get('pullRequest'), dict) else {}
    changed = sorted(set(str(x) for x in (pr.get('changedPaths') or [])))
    if not SHA40.fullmatch(before) or after != target or str(pr.get('mergeCommitSha', '')).lower() != target:
        raise ReconcileError('merge record is not bound to the ledger current source commit')
    if not changed:
        raise ReconcileError('merge record has no reviewed changed-path set')
    if ctx['headSha'] not in {before, target}:
        raise ReconcileError(f'local HEAD {ctx["headSha"]} is neither the pre-merge source {before} nor target merge {target}')

    if fetch:
        refspec = f'refs/heads/{ledger["defaultBranch"]}:refs/remotes/origin/{ledger["defaultBranch"]}'
        run_git(repo_root, 'fetch', '--no-tags', 'origin', refspec)
    remote_ref = f'refs/remotes/origin/{ledger["defaultBranch"]}'
    remote_sha = git_out(repo_root, 'rev-parse', remote_ref).lower()
    if remote_sha != target:
        raise ReconcileError(f'fetched origin/{ledger["defaultBranch"]} is {remote_sha}, expected exact ledger merge {target}')
    if run_git(repo_root, 'merge-base', '--is-ancestor', before, target, check=False).returncode != 0:
        raise ReconcileError('target merge commit is not a descendant of the recorded pre-merge source')

    entries = status_entries(repo_root)
    dirty_source: list[str] = []
    preserved_operational: list[str] = []
    for item in entries:
        xy, rel = item['xy'], item['path']
        if xy == '??' and operational_untracked(rel):
            preserved_operational.append(rel)
            continue
        if xy[0] != ' ' and xy != '??':
            raise ReconcileError(f'staged/index changes are not allowed during checkout reconciliation: {rel}')
        dirty_source.append(rel)
    unexpected = sorted(set(dirty_source) - set(changed))
    if unexpected:
        raise ReconcileError(f'local checkout contains changes outside the reviewed merge transition: {unexpected}')
    for rel in sorted(set(dirty_source) & set(changed)):
        verify_local_expected_bytes(repo_root, target, rel)

    previous = ctx['headSha']
    if previous != target or dirty_source:
        run_git(repo_root, 'reset', '--hard', target)
    final_head = git_out(repo_root, 'rev-parse', 'HEAD').lower()
    if final_head != target:
        raise ReconcileError('local checkout did not land on the exact ledger merge commit')
    post = status_entries(repo_root)
    residual = []
    preserved_after = []
    for item in post:
        if item['xy'] == '??' and operational_untracked(item['path']):
            preserved_after.append(item['path'])
        else:
            residual.append(item)
    if residual:
        raise ReconcileError(f'local checkout is still dirty after reconciliation: {residual}')
    verify_source_integrity(repo_root)
    return {
        'revision': REVISION,
        'repository': ledger['repository'],
        'repositoryId': ledger['repositoryId'],
        'defaultBranch': ledger['defaultBranch'],
        'previousHeadSha': previous,
        'reconciledHeadSha': final_head,
        'mergeStage': merge_record.get('stage'),
        'mergeCommitSha': target,
        'reviewedChangedPaths': changed,
        'dirtyReviewedPathsBefore': sorted(dirty_source),
        'preservedOperationalUntracked': sorted(set(preserved_operational + preserved_after)),
        'sourceIntegrityManifestSha256': hashlib.sha256((repo_root / 'SOURCE_SHA256SUMS.txt').read_bytes()).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Safely fast-forward the local first-real-run checkout to an exact reviewed evidence merge without discarding unrelated source changes.')
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--merge-stage', required=True)
    parser.add_argument('--contract', type=Path, default=CONTRACT)
    parser.add_argument('--token-env', default='MTE_PRODUCTION_CONTROLLER_TOKEN')
    args = parser.parse_args()
    import importlib.util
    handoff_path = ROOT / 'scripts' / 'first_real_run_handoff.py'
    spec = importlib.util.spec_from_file_location('mte_handoff_for_reconcile', handoff_path)
    if spec is None or spec.loader is None:
        raise ReconcileError('could not load first-real-run ledger validator')
    h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
    contract_path = args.contract.resolve(); contract = h.load_contract(contract_path)
    ledger = json.loads(args.ledger.resolve().read_text(encoding='utf-8')); h.validate(ledger, contract, contract_path)
    merge_record = next((r for r in ledger.get('records', []) if r.get('stage') == args.merge_stage), None)
    if not isinstance(merge_record, dict):
        raise ReconcileError(f'ledger has no completed merge stage {args.merge_stage}')
    token = os.environ.get(args.token_env, '').strip()
    if not token:
        raise ReconcileError(f'{args.token_env} is required for live repository identity verification')
    live_repo_snapshot(ledger, token, contract['githubInfrastructureAudit']['apiVersion'])
    result = reconcile_checkout(repo_root=ROOT, ledger=ledger, merge_record=merge_record)
    print(json.dumps({'passed': True, 'reconciliation': result}, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ReconcileError, OSError, ValueError) as exc:
        print(json.dumps({'passed': False, 'error': str(exc)}, indent=2))
        raise SystemExit(2)
