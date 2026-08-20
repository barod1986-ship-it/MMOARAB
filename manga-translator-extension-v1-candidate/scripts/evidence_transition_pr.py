from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HANDOFF_TOOL = ROOT / 'scripts' / 'first_real_run_handoff.py'
DEFAULT_CONTRACT = ROOT / 'release-control' / 'production-execution-contract.json'
REVISION = 'rev30-evidence-transition-pr-v1'
SAFE_RELEASE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$')
SHA40 = re.compile(r'^[0-9a-f]{40}$')


class EvidencePrError(ValueError):
    pass


def _load_handoff():
    spec = importlib.util.spec_from_file_location('mte_handoff_for_evidence_pr', HANDOFF_TOOL)
    if spec is None or spec.loader is None:
        raise EvidencePrError('could not load first-real-run handoff module')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


H = _load_handoff()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def api_request(method: str, url: str, token: str, version: str, payload: Any | None = None) -> tuple[int, Any | None]:
    data = None if payload is None else json.dumps(payload, separators=(',', ':')).encode('utf-8')
    req = urllib.request.Request(url, data=data, method=method, headers={
        'Accept': 'application/vnd.github+json',
        'Authorization': f'Bearer {token}',
        'X-GitHub-Api-Version': version,
        'User-Agent': 'mte-evidence-transition-pr',
        'Content-Type': 'application/json',
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            return response.status, (json.loads(raw.decode('utf-8')) if raw else None)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')[:800]
        raise EvidencePrError(f'GitHub API {method} {url} failed with HTTP {exc.code}: {body}') from exc
    except urllib.error.URLError as exc:
        raise EvidencePrError(f'GitHub API {method} {url} failed: {exc.reason}') from exc


def api_get(url: str, token: str, version: str) -> Any:
    status, payload = api_request('GET', url, token, version)
    if status != 200:
        raise EvidencePrError(f'unexpected GitHub GET status {status}')
    return payload


def repo_base(ledger: dict[str, Any]) -> str:
    owner, repo = str(ledger['repository']).split('/', 1)
    return f'https://api.github.com/repos/{urllib.parse.quote(owner, safe="")}/{urllib.parse.quote(repo, safe="")}'


def local_file_snapshot(paths: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for rel in paths:
        path = (ROOT / rel).resolve()
        try:
            path.relative_to(ROOT.resolve())
        except ValueError as exc:
            raise EvidencePrError(f'evidence path escapes repository root: {rel}') from exc
        if path.is_symlink() or not path.is_file():
            raise EvidencePrError(f'evidence transition path is not a regular file: {rel}')
        data = path.read_bytes()
        out[rel] = {'sha256': sha256_bytes(data), 'sizeBytes': len(data)}
    return out


def transition_key(stage: str) -> str:
    if stage == 'release-evidence-local-promotion':
        return 'release-evidence'
    if stage == 'public-evidence-local-promotion':
        return 'public-evidence'
    raise EvidencePrError(f'{stage} is not a supported local evidence PR transition')


def make_branch_name(stage: str, ledger: dict[str, Any], nonce: str) -> str:
    release_id = str(ledger['releaseId'])
    if not SAFE_RELEASE.fullmatch(release_id):
        raise EvidencePrError('releaseId is not safe for a Git branch name')
    if not nonce.startswith('mte-pr-') or not re.fullmatch(r'mte-pr-[0-9a-f]{16,64}', nonce):
        raise EvidencePrError('invalid evidence PR intent nonce')
    return f'evidence/{transition_key(stage)}/{release_id}-{ledger["currentSourceHeadSha"][:12]}-{nonce[7:23]}'


def pending_snapshot(stage: str, ledger: dict[str, Any], contract: dict[str, Any], nonce: str) -> dict[str, Any]:
    changed = H.verify_local_promotion(stage, ledger, contract)
    return {
        'revision': REVISION,
        'stage': stage,
        'sourceHeadSha': ledger['currentSourceHeadSha'],
        'allowlist': contract['firstRealRun']['stageLaunchHints'][stage]['allowlist'],
        'branch': make_branch_name(stage, ledger, nonce),
        'prIntentNonce': nonce,
        'changedPaths': changed,
        'files': local_file_snapshot(changed),
    }


def validate_pending(pending: dict[str, Any], stage: str, ledger: dict[str, Any], contract: dict[str, Any]) -> None:
    if pending.get('revision') != REVISION or pending.get('stage') != stage:
        raise EvidencePrError('pending evidence PR revision/stage mismatch')
    if pending.get('sourceHeadSha') != ledger['currentSourceHeadSha']:
        raise EvidencePrError('pending evidence PR belongs to a different source commit')
    expected = pending_snapshot(stage, ledger, contract, str(pending.get('prIntentNonce', '')))
    for key in ('allowlist', 'branch', 'changedPaths', 'files'):
        if pending.get(key) != expected.get(key):
            raise EvidencePrError(f'pending evidence PR {key} no longer matches the local promotion output')


def assert_operator_and_repo(ledger: dict[str, Any], token: str, version: str) -> dict[str, str]:
    base = repo_base(ledger)
    meta = api_get(base, token, version)
    if str(meta.get('id', '')) != str(ledger['repositoryId']):
        raise EvidencePrError('live repository id differs from the sealed ledger repository identity')
    if str(meta.get('default_branch', '')) != str(ledger['defaultBranch']):
        raise EvidencePrError('live repository default branch differs from the sealed ledger')
    actor = api_get('https://api.github.com/user', token, version)
    actor_id = str(actor.get('id', ''))
    if actor_id not in {str(x) for x in ledger['authorizedOperatorIds']}:
        raise EvidencePrError('authenticated GitHub operator is not in the sealed production operator allowlist')
    branch = urllib.parse.quote(str(ledger['defaultBranch']), safe='')
    branch_obj = api_get(f'{base}/branches/{branch}', token, version)
    live_sha = str(((branch_obj or {}).get('commit') or {}).get('sha', '')).lower()
    if live_sha != str(ledger['currentSourceHeadSha']).lower():
        raise EvidencePrError('default branch moved before evidence PR creation')
    return {'id': actor_id, 'login': str(actor.get('login', ''))}


def find_pr_for_branch(ledger: dict[str, Any], branch: str, token: str, version: str) -> list[dict[str, Any]]:
    owner = str(ledger['repository']).split('/', 1)[0]
    query = urllib.parse.urlencode({'state': 'all', 'head': f'{owner}:{branch}', 'base': ledger['defaultBranch'], 'per_page': 100})
    payload = api_get(f'{repo_base(ledger)}/pulls?{query}', token, version)
    if not isinstance(payload, list):
        raise EvidencePrError('unexpected pull request list response')
    return [x for x in payload if isinstance(x, dict)]


def get_ref_sha(ledger: dict[str, Any], branch: str, token: str, version: str) -> str | None:
    encoded = urllib.parse.quote(f'heads/{branch}', safe='')
    try:
        ref = api_get(f'{repo_base(ledger)}/git/ref/{encoded}', token, version)
    except EvidencePrError as exc:
        if 'HTTP 404' in str(exc):
            return None
        raise
    sha = str(((ref or {}).get('object') or {}).get('sha', '')).lower()
    return sha if SHA40.fullmatch(sha) else None


def remote_file_snapshot(ledger: dict[str, Any], head_sha: str, paths: list[str], token: str, version: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for rel in paths:
        quoted = urllib.parse.quote(rel, safe='/')
        payload = api_get(f'{repo_base(ledger)}/contents/{quoted}?ref={urllib.parse.quote(head_sha, safe="")}', token, version)
        if payload.get('type') != 'file' or payload.get('encoding') != 'base64':
            raise EvidencePrError(f'cannot verify remote evidence file bytes: {rel}')
        raw = base64.b64decode(str(payload.get('content', '')).replace('\n', ''), validate=True)
        out[rel] = {'sha256': sha256_bytes(raw), 'sizeBytes': len(raw)}
    return out


def verify_created_pr(*, ledger: dict[str, Any], stage: str, pr: dict[str, Any], expected_head_sha: str, expected_branch: str, expected_files: dict[str, dict[str, Any]], contract: dict[str, Any], token: str, version: str) -> dict[str, Any]:
    if str(pr.get('base', {}).get('ref', '')) != ledger['defaultBranch']:
        raise EvidencePrError('evidence PR base branch is not the sealed default branch')
    if str(pr.get('head', {}).get('ref', '')) != expected_branch:
        raise EvidencePrError('evidence PR head branch does not match the sealed transition branch')
    head_sha = str(pr.get('head', {}).get('sha', '')).lower()
    if head_sha != expected_head_sha:
        raise EvidencePrError('evidence PR head SHA does not match the sealed transition commit')
    allow_name = str(contract['firstRealRun']['stageLaunchHints'][stage]['allowlist'])
    allow_cfg = contract['firstRealRun']['sourceTransitionAllowlists'][allow_name]
    pr_number = int(pr.get('number', 0))
    files_payload = api_get(f'{repo_base(ledger)}/pulls/{pr_number}/files?per_page=100', token, version)
    changed = {str(x.get('filename', '')) for x in files_payload if isinstance(x, dict)}
    if changed != set(expected_files):
        raise EvidencePrError(f'evidence PR changed path set differs from the sealed local promotion: {sorted(changed ^ set(expected_files))}')
    if not set(allow_cfg['requiredPaths']).issubset(changed) or not changed.issubset(set(allow_cfg['paths'])):
        raise EvidencePrError('evidence PR files do not satisfy the transition allowlist')
    commit = api_get(f'{repo_base(ledger)}/commits/{head_sha}', token, version)
    parents = commit.get('parents') or []
    parent_sha = str((parents[0] if parents else {}).get('sha', '')).lower() if isinstance(parents[0] if parents else {}, dict) else ''
    if len(parents) != 1 or parent_sha != ledger['currentSourceHeadSha']:
        raise EvidencePrError('evidence PR head commit is not a single-parent child of the sealed source commit')
    remote = remote_file_snapshot(ledger, head_sha, sorted(changed), token, version)
    if remote != expected_files:
        raise EvidencePrError('evidence PR remote file bytes differ from the sealed local promotion bytes')
    return {
        'prNumber': pr_number,
        'url': str(pr.get('html_url', '')),
        'headRef': expected_branch,
        'headSha': head_sha,
        'baseRef': ledger['defaultBranch'],
        'baseSha': ledger['currentSourceHeadSha'],
        'allowlist': allow_name,
        'changedPaths': sorted(changed),
        'files': expected_files,
    }


def create_commit_from_files(ledger: dict[str, Any], stage: str, pending: dict[str, Any], token: str, version: str) -> str:
    base = repo_base(ledger)
    base_commit = api_get(f'{base}/git/commits/{ledger["currentSourceHeadSha"]}', token, version)
    base_tree = str((base_commit.get('tree') or {}).get('sha', ''))
    if not SHA40.fullmatch(base_tree):
        raise EvidencePrError('default branch commit has no valid Git tree SHA')
    entries = []
    for rel in pending['changedPaths']:
        raw = (ROOT / rel).read_bytes()
        status, blob = api_request('POST', f'{base}/git/blobs', token, version, {'content': base64.b64encode(raw).decode('ascii'), 'encoding': 'base64'})
        if status != 201 or not isinstance(blob, dict) or not SHA40.fullmatch(str(blob.get('sha', ''))):
            raise EvidencePrError(f'could not create Git blob for {rel}')
        entries.append({'path': rel, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']})
    status, tree = api_request('POST', f'{base}/git/trees', token, version, {'base_tree': base_tree, 'tree': entries})
    if status != 201 or not isinstance(tree, dict) or not SHA40.fullmatch(str(tree.get('sha', ''))):
        raise EvidencePrError('could not create evidence Git tree')
    message = f'Promote {transition_key(stage)} for {ledger["releaseId"]}'
    status, commit = api_request('POST', f'{base}/git/commits', token, version, {'message': message, 'tree': tree['sha'], 'parents': [ledger['currentSourceHeadSha']]})
    sha = str((commit or {}).get('sha', '')).lower()
    if status != 201 or not SHA40.fullmatch(sha):
        raise EvidencePrError('could not create evidence Git commit')
    return sha


def create_or_recover(*, ledger: dict[str, Any], stage: str, pending: dict[str, Any], contract: dict[str, Any], token: str, version: str) -> dict[str, Any]:
    validate_pending(pending, stage, ledger, contract)
    actor = assert_operator_and_repo(ledger, token, version)
    branch = str(pending['branch'])
    existing_sha = get_ref_sha(ledger, branch, token, version)
    if existing_sha is None:
        head_sha = create_commit_from_files(ledger, stage, pending, token, version)
        status, _ = api_request('POST', f'{repo_base(ledger)}/git/refs', token, version, {'ref': f'refs/heads/{branch}', 'sha': head_sha})
        if status != 201:
            raise EvidencePrError('could not create evidence transition branch')
    else:
        head_sha = existing_sha

    prs = find_pr_for_branch(ledger, branch, token, version)
    if len(prs) > 1:
        raise EvidencePrError('multiple pull requests exist for the sealed evidence transition branch')
    if prs:
        pr = prs[0]
    else:
        title = f'Promote {transition_key(stage)} ({ledger["releaseId"]})'
        body = f'Content-addressed evidence-only transition for {ledger["releaseId"]}. Base source: {ledger["currentSourceHeadSha"]}. Intent: {pending["prIntentNonce"]}. Runtime source changes are forbidden by the sealed allowlist.'
        status, pr = api_request('POST', f'{repo_base(ledger)}/pulls', token, version, {'title': title, 'head': branch, 'base': ledger['defaultBranch'], 'body': body, 'draft': False})
        if status != 201 or not isinstance(pr, dict):
            raise EvidencePrError('could not create evidence transition pull request')
    verified = verify_created_pr(ledger=ledger, stage=stage, pr=pr, expected_head_sha=head_sha, expected_branch=branch, expected_files=pending['files'], contract=contract, token=token, version=version)
    verified['creator'] = actor
    verified['prIntentNonce'] = pending['prIntentNonce']
    return verified


def main() -> int:
    parser = argparse.ArgumentParser(description='Create/recover an allowlisted evidence-only PR from a verified local promotion without git push.')
    parser.add_argument('--contract', type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--stage', choices=['release-evidence-local-promotion', 'public-evidence-local-promotion'], required=True)
    parser.add_argument('--pending', type=Path, required=True, help='Sealed pending evidence-PR plan generated by the controller.')
    parser.add_argument('--token-env', default='MTE_PRODUCTION_CONTROLLER_TOKEN')
    args = parser.parse_args()
    contract_path = args.contract.resolve()
    contract = H.load_contract(contract_path)
    ledger = json.loads(args.ledger.read_text(encoding='utf-8'))
    H.validate(ledger, contract, contract_path)
    pending = json.loads(args.pending.read_text(encoding='utf-8'))
    token = os.environ.get(args.token_env, '').strip()
    if not token:
        raise EvidencePrError(f'{args.token_env} is required')
    result = create_or_recover(ledger=ledger, stage=args.stage, pending=pending, contract=contract, token=token, version=contract['githubInfrastructureAudit']['apiVersion'])
    print(json.dumps({'passed': True, 'revision': REVISION, 'pullRequest': result}, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (EvidencePrError, H.HandoffError, OSError, ValueError) as exc:
        print(json.dumps({'passed': False, 'error': str(exc)}, indent=2))
        raise SystemExit(2)
