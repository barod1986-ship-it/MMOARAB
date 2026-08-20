from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / 'release-control' / 'production-execution-contract.json'
PROVISION_TOOL = ROOT / 'scripts' / 'provision_github_production_infrastructure.py'
RECOVERY_TOOL = ROOT / 'scripts' / 'first_real_run_recovery.py'
LEDGER_REVISION = 'rev32-first-real-run-ledger-v10'
CONTRACT_REVISION = 'rev34-recovery-rotation-offsite-durability-v1'
SHA40 = __import__('re').compile(r'^[0-9a-f]{40}$')


class HandoffError(ValueError):
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
        raise HandoffError('unsupported production execution contract revision')
    return value


def load_bound_onboarding(path: Path, contract: dict[str, Any], contract_path: Path) -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location('mte_provision_for_handoff', PROVISION_TOOL)
    if spec is None or spec.loader is None:
        raise HandoffError('could not load production infrastructure provisioner')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cfg = json.loads(path.read_text(encoding='utf-8'))
    try:
        module.validate_config(cfg, contract, contract_path, require_binding=True)
    except Exception as exc:
        raise HandoffError(f'onboarding config is not valid/bound: {exc}') from exc
    return cfg


def without_hash(ledger: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in ledger.items() if k != 'ledgerSha256'}


def seal(ledger: dict[str, Any]) -> dict[str, Any]:
    value = dict(without_hash(ledger))
    value['ledgerSha256'] = sha256_bytes(canonical(value))
    return value


def stage_plan(ledger: dict[str, Any], contract: dict[str, Any]) -> list[str]:
    plan = (contract['firstRealRun'].get('stagePlans') or {}).get(ledger.get('releaseClass'))
    if not isinstance(plan, list) or not plan:
        raise HandoffError(f"no first-real-run stage plan for release class {ledger.get('releaseClass')!r}")
    return [str(x) for x in plan]


def validate(ledger: dict[str, Any], contract: dict[str, Any], contract_path: Path) -> None:
    if ledger.get('schemaVersion') != 4 or ledger.get('revision') != LEDGER_REVISION:
        raise HandoffError('unsupported first-real-run ledger schema/revision')
    if ledger.get('contractSha256') != file_sha256(contract_path):
        raise HandoffError('ledger is bound to a different production execution contract')
    if not ledger.get('onboardingConfigSha256') or not ledger.get('repositoryId') or not ledger.get('repository'):
        raise HandoffError('ledger is missing repository onboarding identity binding')
    operators = ledger.get('authorizedOperatorIds')
    operator_logins = ledger.get('authorizedOperatorLogins')
    if not isinstance(operators, list) or not operators or not all(str(x).isdigit() for x in operators):
        raise HandoffError('ledger is missing authorized production operator ids')
    if not isinstance(operator_logins, list) or not operator_logins:
        raise HandoffError('ledger is missing authorized production operator logins')
    expected_hash = seal(ledger)['ledgerSha256']
    if ledger.get('ledgerSha256') != expected_hash:
        raise HandoffError('ledgerSha256 mismatch')
    stages = stage_plan(ledger, contract)
    records = ledger.get('records') or []
    if len(records) > len(stages):
        raise HandoffError('ledger contains too many stage records')
    cursor = str(ledger.get('initialSourceHeadSha', '')).lower()
    if not SHA40.fullmatch(cursor):
        raise HandoffError('initialSourceHeadSha is invalid')
    transitions = set(contract['firstRealRun'].get('sourceCommitTransitionStages') or [])
    for index, record in enumerate(records):
        stage = stages[index]
        if record.get('stage') != stage:
            raise HandoffError('ledger stage order is invalid')
        if record.get('status') != 'success':
            raise HandoffError('only successful stages may be committed to the handoff ledger')
        if record.get('sourceHeadShaBefore') != cursor:
            raise HandoffError(f'ledger source commit chain is invalid at {stage}')
        if stage in contract['firstRealRun'].get('manualReviewBoundaries', []):
            if record.get('manualReviewed') is not True:
                raise HandoffError(f'manual review flag missing for {stage}')
            checkpoint = record.get('manualCheckpoint')
            if not isinstance(checkpoint, dict):
                raise HandoffError(f'content-addressed manual checkpoint missing for {stage}')
            module = load_manual_checkpoint_module()
            try:
                module.validate_checkpoint(checkpoint, stage=stage, ledger={**ledger, 'currentSourceHeadSha': cursor})
            except Exception as exc:
                raise HandoffError(f'manual checkpoint validation failed for {stage}: {exc}') from exc
        if stage in transitions:
            after = str(record.get('sourceHeadShaAfter', '')).lower()
            if not SHA40.fullmatch(after) or after == cursor:
                raise HandoffError(f'commit transition is invalid at {stage}')
            cursor = after
        elif record.get('sourceHeadShaAfter') not in (None, cursor):
            raise HandoffError(f'non-transition stage unexpectedly changed source commit at {stage}')
    # Post-merge local checkout reconciliation is a provenance checkpoint, not a source transition.
    for record in records:
        hint = contract['firstRealRun'].get('stageLaunchHints', {}).get(record.get('stage')) or {}
        if hint.get('kind') != 'local-checkout-reconciliation':
            continue
        value = record.get('checkoutReconciliation')
        if not isinstance(value, dict) or value.get('revision') != 'rev31-post-merge-checkout-reconciliation-v1':
            raise HandoffError(f"stage {record.get('stage')} is missing a valid checkout reconciliation snapshot")
        if str(value.get('reconciledHeadSha', '')).lower() != str(record.get('sourceHeadShaBefore', '')).lower():
            raise HandoffError(f"checkout reconciliation at {record.get('stage')} is not bound to the ledger source cursor")
        if value.get('mergeStage') != hint.get('mergeStage'):
            raise HandoffError(f"checkout reconciliation at {record.get('stage')} references the wrong merge stage")
        merge_record = next((x for x in records if x.get('stage') == hint.get('mergeStage')), None)
        merge_pr = merge_record.get('pullRequest') if isinstance(merge_record, dict) and isinstance(merge_record.get('pullRequest'), dict) else {}
        if sorted(value.get('reviewedChangedPaths') or []) != sorted(merge_pr.get('changedPaths') or []):
            raise HandoffError(f"checkout reconciliation at {record.get('stage')} changed-path binding differs from the reviewed merge")
        digest = str(value.get('sourceIntegrityManifestSha256', ''))
        if not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise HandoffError(f"checkout reconciliation at {record.get('stage')} is missing the post-reconciliation Source Integrity manifest hash")

    created_pr_kinds = {'evidence-pr-created'}
    for record in records:
        hint = contract['firstRealRun'].get('stageLaunchHints', {}).get(record.get('stage')) or {}
        if hint.get('kind') in created_pr_kinds or created_pr_config(str(record.get('stage')), contract):
            pr = record.get('pullRequestCreated')
            if not isinstance(pr, dict) or int(pr.get('prNumber', 0)) <= 0 or not SHA40.fullmatch(str(pr.get('headSha', '')).lower()):
                raise HandoffError(f"stage {record.get('stage')} is missing a sealed pull request creation identity")
    automated = {'workflow', 'workflow-set'}
    for record in records:
        hint = contract['firstRealRun'].get('stageLaunchHints', {}).get(record.get('stage')) or {}
        if hint.get('kind') in automated:
            nonce = str(record.get('runIntentNonce', ''))
            if not nonce.startswith('mte-') or len(nonce) < 12:
                raise HandoffError(f"automated stage {record.get('stage')} is missing a valid run intent nonce")
            observations = record.get('runObservations') or []
            if not observations:
                raise HandoffError(f"automated stage {record.get('stage')} is missing run observations")
            if any(nonce not in str(obs.get('displayTitle', '')) for obs in observations):
                raise HandoffError(f"automated stage {record.get('stage')} run observation is not bound to its intent nonce")
    # Recovery summaries are part of the operational provenance chain. The handoff
    # validator checks their sealed identity structurally; the controller additionally
    # re-opens every local snapshot and verifies all bytes before continuation.
    recovery_revision = str((contract['firstRealRun'].get('recovery') or {}).get('revision', ''))
    manual_stages = set(contract['firstRealRun'].get('manualReviewBoundaries') or [])
    verified_recovery_stages: dict[str, str] = {}
    for record in records:
        stage = str(record.get('stage', ''))
        hint = contract['firstRealRun'].get('stageLaunchHints', {}).get(stage) or {}
        needs_recovery = hint.get('kind') in automated or stage in manual_stages
        if not needs_recovery:
            continue
        summary = record.get('recoverySnapshot')
        ref = record.get('recoverySnapshotRef')
        if isinstance(summary, dict):
            if summary.get('revision') != recovery_revision or summary.get('stage') != stage:
                raise HandoffError(f'recovery snapshot identity is invalid for {stage}')
            digest = str(summary.get('manifestSha256', ''))
            if not re.fullmatch(r'[0-9a-f]{64}', digest):
                raise HandoffError(f'recovery snapshot manifest hash is invalid for {stage}')
            if not str(summary.get('relativePath', '')):
                raise HandoffError(f'recovery snapshot path is missing for {stage}')
            verified_recovery_stages[stage] = digest
        elif isinstance(ref, dict):
            source_stage = str(ref.get('stage', ''))
            digest = str(ref.get('manifestSha256', ''))
            if verified_recovery_stages.get(source_stage) != digest:
                raise HandoffError(f'recovery snapshot reference is invalid for {stage}')
            verified_recovery_stages[stage] = digest
        else:
            raise HandoffError(f'disaster-recovery snapshot/reference missing for {stage}')

    pending = ledger.get('pendingLaunch')
    if pending is not None:
        if not isinstance(pending, dict) or pending.get('stage') != (stages[len(records)] if len(records) < len(stages) else None):
            raise HandoffError('pending launch is not bound to the next ledger stage')
        if pending.get('sourceHeadSha') != cursor:
            raise HandoffError('pending launch source commit does not match the ledger cursor')
        nonce = str(pending.get('runIntentNonce', ''))
        if not nonce.startswith('mte-') or len(nonce) < 12:
            raise HandoffError('pending launch has an invalid run intent nonce')
        dispatches = pending.get('dispatches')
        if not isinstance(dispatches, list) or not dispatches:
            raise HandoffError('pending launch must declare its workflow dispatches')
    pending_pr = ledger.get('pendingEvidencePr')
    if pending_pr is not None:
        next_name = stages[len(records)] if len(records) < len(stages) else None
        if not isinstance(pending_pr, dict) or pending_pr.get('stage') != next_name:
            raise HandoffError('pending evidence PR is not bound to the next ledger stage')
        if pending_pr.get('sourceHeadSha') != cursor:
            raise HandoffError('pending evidence PR source commit does not match the ledger cursor')
        if not str(pending_pr.get('prIntentNonce', '')).startswith('mte-pr-'):
            raise HandoffError('pending evidence PR has an invalid intent nonce')
    if str(ledger.get('currentSourceHeadSha', '')).lower() != cursor:
        raise HandoffError('currentSourceHeadSha does not match the verified transition chain')


def next_stage(ledger: dict[str, Any], contract: dict[str, Any]) -> str | None:
    stages = stage_plan(ledger, contract)
    index = len(ledger.get('records') or [])
    return stages[index] if index < len(stages) else None


def stage_hint(stage: str | None, contract: dict[str, Any]) -> Any:
    return None if stage is None else contract['firstRealRun'].get('stageLaunchHints', {}).get(stage)


def write(path: Path, ledger: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(seal(ledger), indent=2) + '\n', encoding='utf-8')


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def api_get(url: str, token: str, api_version: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={
        'Accept': 'application/vnd.github+json',
        'Authorization': f'Bearer {token}',
        'X-GitHub-Api-Version': api_version,
        'User-Agent': 'mte-first-real-run-handoff',
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')[:500]
        raise HandoffError(f'GitHub API request failed with HTTP {exc.code}: {body}') from exc
    except urllib.error.URLError as exc:
        raise HandoffError(f'GitHub API request failed: {exc.reason}') from exc


def api_get_paginated(url: str, token: str, api_version: str, *, per_page: int = 100) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        sep = '&' if '?' in url else '?'
        payload = api_get(f'{url}{sep}per_page={per_page}&page={page}', token, api_version)
        if not isinstance(payload, list):
            raise HandoffError('expected a paginated GitHub list response')
        out.extend(x for x in payload if isinstance(x, dict))
        if len(payload) < per_page:
            break
        page += 1
        if page > 1000:
            raise HandoffError('GitHub pagination safety limit exceeded')
    return out


def repository_base(ledger: dict[str, Any]) -> str:
    owner, repo = str(ledger['repository']).split('/', 1)
    return f'https://api.github.com/repos/{urllib.parse.quote(owner, safe="")}/{urllib.parse.quote(repo, safe="")}'


def load_run_observation(run_id: str, ledger: dict[str, Any], contract: dict[str, Any], token: str | None, snapshot_dir: Path | None) -> dict[str, Any]:
    if snapshot_dir is not None:
        path = snapshot_dir / f'{run_id}.json'
        if not path.is_file():
            raise HandoffError(f'run snapshot missing: {path}')
        return json.loads(path.read_text(encoding='utf-8'))
    if not token:
        raise HandoffError('live run verification requires a token')
    return api_get(f'{repository_base(ledger)}/actions/runs/{urllib.parse.quote(run_id, safe="")}', token, contract['githubInfrastructureAudit']['apiVersion'])


def workflow_matches(path_value: str, expected: str) -> bool:
    return expected in path_value or Path(expected).name in path_value


def verify_run_stage(stage: str, run_ids: list[str], ledger: dict[str, Any], contract: dict[str, Any], token: str | None, snapshot_dir: Path | None, expected_nonce: str | None = None) -> list[dict[str, Any]]:
    hint = contract['firstRealRun']['stageLaunchHints'].get(stage) or {}
    kind = hint.get('kind')
    if kind not in {'workflow', 'workflow-set'}:
        raise HandoffError(f'{stage} is not an automated workflow stage')
    minimum = int(contract['firstRealRun'].get('runIdMinimums', {}).get(stage, 0))
    if len(run_ids) < minimum:
        raise HandoffError(f'{stage} requires at least {minimum} recorded workflow run id(s)')
    if kind == 'workflow' and len(run_ids) != 1:
        raise HandoffError(f'{stage} requires exactly one workflow run id')
    expected_workflows = [hint['workflow']] if kind == 'workflow' else list(hint.get('workflows') or [])
    if kind == 'workflow-set' and len(run_ids) != len(expected_workflows):
        raise HandoffError(f'{stage} requires exactly {len(expected_workflows)} workflow run ids')
    observed: list[dict[str, Any]] = []
    seen_workflows: set[str] = set()
    operators = {str(x) for x in ledger['authorizedOperatorIds']}
    for run_id in run_ids:
        run = load_run_observation(run_id, ledger, contract, token, snapshot_dir)
        conclusion = str(run.get('conclusion', ''))
        event = str(run.get('event', ''))
        head_sha = str(run.get('head_sha', '')).lower()
        head_branch = str(run.get('head_branch', ''))
        path_value = str(run.get('path') or run.get('workflow_path') or '')
        actor_obj = run.get('actor') if isinstance(run.get('actor'), dict) else {}
        actor = str(actor_obj.get('login') or run.get('actor_login') or '')
        actor_id = str(actor_obj.get('id') or run.get('actor_id') or '')
        title = str(run.get('display_title') or run.get('name') or '')
        if conclusion != 'success':
            raise HandoffError(f'workflow run {run_id} did not conclude success')
        if event != 'workflow_dispatch':
            raise HandoffError(f'workflow run {run_id} was not workflow_dispatch')
        if head_sha != ledger['currentSourceHeadSha']:
            raise HandoffError(f'workflow run {run_id} head_sha does not match current ledger source commit')
        if head_branch != ledger['defaultBranch']:
            raise HandoffError(f'workflow run {run_id} did not run on default branch {ledger["defaultBranch"]}')
        if actor_id not in operators:
            raise HandoffError(f'workflow run {run_id} actor id is not in the sealed production operator allowlist')
        matched = next((wf for wf in expected_workflows if workflow_matches(path_value, wf)), None)
        if matched is None:
            raise HandoffError(f'workflow run {run_id} came from an unexpected workflow: {path_value}')
        if matched in seen_workflows:
            raise HandoffError(f'duplicate workflow evidence for {matched} at {stage}')
        seen_workflows.add(matched)
        title_token = hint.get('displayTitleContains')
        if title_token and str(title_token).lower() not in title.lower():
            raise HandoffError(f'workflow run {run_id} display title does not prove {stage} mode')
        if expected_nonce and expected_nonce not in title:
            raise HandoffError(f'workflow run {run_id} display title does not contain the sealed run intent nonce')
        observed.append({'runId': str(run_id), 'workflow': matched, 'actor': actor, 'actorId': actor_id, 'headSha': head_sha, 'headBranch': head_branch, 'displayTitle': title})
    if set(expected_workflows) != seen_workflows:
        missing = sorted(set(expected_workflows) - seen_workflows)
        raise HandoffError(f'{stage} is missing required workflow run(s): {missing}')
    return observed


def record_for_stage(ledger: dict[str, Any], stage: str) -> dict[str, Any]:
    for record in ledger.get('records') or []:
        if record.get('stage') == stage:
            return record
    raise HandoffError(f'ledger has no completed record for stage {stage}')


def created_pr_config(stage: str, contract: dict[str, Any]) -> dict[str, Any] | None:
    hint = contract['firstRealRun']['stageLaunchHints'].get(stage) or {}
    cfg = hint.get('createdPullRequest')
    return cfg if isinstance(cfg, dict) else None


def expected_created_pr_branch(stage: str, nonce: str, ledger: dict[str, Any], contract: dict[str, Any]) -> str:
    cfg = created_pr_config(stage, contract)
    if not cfg:
        raise HandoffError(f'{stage} does not declare a workflow-created pull request contract')
    prefix = str(cfg.get('headBranchPrefix', ''))
    source_stage = str(cfg.get('headBranchDerivedRunStage', ''))
    source = record_for_stage(ledger, source_stage)
    runs = source.get('runObservations') or []
    if len(runs) != 1:
        raise HandoffError(f'{source_stage} must contain exactly one run observation to derive the evidence PR branch')
    branch = prefix + str(runs[0]['runId'])
    if cfg.get('headBranchIncludesRunIntentNonce'):
        branch += '-' + nonce
    return branch


def load_created_pr_observation(stage: str, nonce: str, ledger: dict[str, Any], contract: dict[str, Any], token: str | None, snapshot: Path | None) -> dict[str, Any]:
    expected_branch = expected_created_pr_branch(stage, nonce, ledger, contract)
    if snapshot is not None:
        return json.loads(snapshot.read_text(encoding='utf-8'))
    if not token:
        raise HandoffError('live created-PR verification requires a token')
    base = repository_base(ledger)
    version = contract['githubInfrastructureAudit']['apiVersion']
    owner = ledger['repository'].split('/', 1)[0]
    query = urllib.parse.urlencode({'state': 'all', 'head': f'{owner}:{expected_branch}', 'base': ledger['defaultBranch'], 'per_page': 100})
    prs = api_get(f'{base}/pulls?{query}', token, version)
    if not isinstance(prs, list) or len(prs) != 1:
        raise HandoffError(f'expected exactly one evidence PR for branch {expected_branch}, found {len(prs) if isinstance(prs,list) else "invalid"}')
    pr = prs[0]
    number = int(pr.get('number', 0))
    head_sha = str((pr.get('head') or {}).get('sha', '')).lower()
    commit = api_get(f'{base}/commits/{head_sha}', token, version)
    files = api_get_paginated(f'{base}/pulls/{number}/files', token, version, per_page=100)
    return {'pullRequest': pr, 'headCommit': commit, 'files': files}


def verify_created_pr_stage(stage: str, nonce: str, ledger: dict[str, Any], contract: dict[str, Any], token: str | None, snapshot: Path | None) -> dict[str, Any]:
    cfg = created_pr_config(stage, contract)
    if not cfg:
        raise HandoffError(f'{stage} does not create a pull request')
    obs = load_created_pr_observation(stage, nonce, ledger, contract, token, snapshot)
    pr = obs.get('pullRequest') or {}
    commit = obs.get('headCommit') or {}
    files = obs.get('files') or []
    expected_branch = expected_created_pr_branch(stage, nonce, ledger, contract)
    if str((pr.get('base') or {}).get('ref', '')) != ledger['defaultBranch']:
        raise HandoffError('created evidence PR base is not the sealed default branch')
    head = pr.get('head') if isinstance(pr.get('head'), dict) else {}
    if str(head.get('ref', '')) != expected_branch:
        raise HandoffError('created evidence PR head branch does not match the sealed run intent')
    head_repo = head.get('repo') if isinstance(head.get('repo'), dict) else {}
    if head_repo and str(head_repo.get('full_name', '')).lower() != str(ledger['repository']).lower():
        raise HandoffError('created evidence PR comes from a different repository')
    head_sha = str(head.get('sha', '')).lower()
    if not SHA40.fullmatch(head_sha) or str(commit.get('sha', '')).lower() != head_sha:
        raise HandoffError('created evidence PR head commit identity is invalid')
    parents = commit.get('parents') or []
    parent = str((parents[0] if parents else {}).get('sha', '')).lower() if isinstance(parents[0] if parents else {}, dict) else ''
    if len(parents) != 1 or parent != ledger['currentSourceHeadSha']:
        raise HandoffError('created evidence PR head is not a single-parent child of the current source commit')
    allow_name = str(cfg.get('allowlist', ''))
    allow_cfg = contract['firstRealRun']['sourceTransitionAllowlists'][allow_name]
    changed: set[str] = set()
    for item in files:
        if not isinstance(item, dict) or str(item.get('status', '')) == 'removed':
            raise HandoffError('created evidence PR contains a removed/invalid file')
        changed.add(str(item.get('filename', '')))
    if not changed or not changed.issubset(set(allow_cfg['paths'])):
        raise HandoffError(f'created evidence PR changed files outside {allow_name}')
    if not set(allow_cfg['requiredPaths']).issubset(changed):
        raise HandoffError('created evidence PR is missing required evidence paths')
    return {'prNumber': int(pr.get('number', 0)), 'url': str(pr.get('html_url', '')), 'headRef': expected_branch, 'headSha': head_sha, 'baseRef': ledger['defaultBranch'], 'baseSha': ledger['currentSourceHeadSha'], 'allowlist': allow_name, 'changedPaths': sorted(changed)}


def load_pr_observation(pr_number: int, ledger: dict[str, Any], contract: dict[str, Any], token: str | None, snapshot: Path | None) -> dict[str, Any]:
    if snapshot is not None:
        return json.loads(snapshot.read_text(encoding='utf-8'))
    if not token:
        raise HandoffError('live PR-merge verification requires a token')
    base = repository_base(ledger)
    version = contract['githubInfrastructureAudit']['apiVersion']
    pr = api_get(f'{base}/pulls/{pr_number}', token, version)
    if not pr.get('merged_at'):
        return {'pullRequest': pr, 'mergeCommit': {}, 'files': []}
    merge_sha = str(pr.get('merge_commit_sha', '')).lower()
    if not SHA40.fullmatch(merge_sha):
        raise HandoffError('merged PR has no valid merge_commit_sha')
    commit = api_get(f'{base}/commits/{merge_sha}', token, version)
    files = api_get_paginated(f'{base}/pulls/{pr_number}/files', token, version, per_page=100)
    return {'pullRequest': pr, 'mergeCommit': commit, 'files': files}


def verify_pr_transition(stage: str, pr_number: int, ledger: dict[str, Any], contract: dict[str, Any], token: str | None, snapshot: Path | None, observation: dict[str, Any] | None = None) -> dict[str, Any]:
    hint = contract['firstRealRun']['stageLaunchHints'].get(stage) or {}
    if hint.get('kind') != 'merged-pr-transition':
        raise HandoffError(f'{stage} is not a merged-PR source transition stage')
    created_stage = str(hint.get('prCreatedStage', ''))
    created_record = record_for_stage(ledger, created_stage) if created_stage else {}
    created = created_record.get('pullRequestCreated') if isinstance(created_record.get('pullRequestCreated'), dict) else None
    if not created:
        raise HandoffError(f'{stage} has no previously recorded pull request creation identity')
    if int(created.get('prNumber', 0)) != int(pr_number):
        raise HandoffError('merge candidate PR number differs from the recorded evidence PR')
    obs = observation if observation is not None else load_pr_observation(pr_number, ledger, contract, token, snapshot)
    pr = obs.get('pullRequest') or {}
    commit = obs.get('mergeCommit') or {}
    files = obs.get('files') or []
    if not pr.get('merged_at'):
        raise HandoffError(f'PR #{pr_number} is not merged')
    head = pr.get('head') if isinstance(pr.get('head'), dict) else {}
    if str(head.get('sha', '')).lower() != str(created.get('headSha', '')).lower() or str(head.get('ref', '')) != str(created.get('headRef', '')):
        raise HandoffError('merged PR head identity differs from the pull request that was recorded for review')
    base = pr.get('base') if isinstance(pr.get('base'), dict) else {}
    if str(base.get('ref', '')) != ledger['defaultBranch']:
        raise HandoffError(f'PR #{pr_number} was not merged into default branch {ledger["defaultBranch"]}')
    merge_sha = str(pr.get('merge_commit_sha', '')).lower()
    if not SHA40.fullmatch(merge_sha) or str(commit.get('sha', '')).lower() != merge_sha:
        raise HandoffError('PR merge commit identity is invalid')
    parents = commit.get('parents') or []
    first_parent = str((parents[0] if parents else {}).get('sha', '')).lower() if isinstance(parents[0] if parents else {}, dict) else ''
    if first_parent != ledger['currentSourceHeadSha']:
        raise HandoffError('PR merge commit is not a direct transition from the ledger current source commit; rebase/recreate the evidence PR')
    allow_name = str(hint.get('allowlist', ''))
    allow_cfg = (contract['firstRealRun'].get('sourceTransitionAllowlists') or {}).get(allow_name) or {}
    allowed = set(str(x) for x in allow_cfg.get('paths', []))
    required = set(str(x) for x in allow_cfg.get('requiredPaths', []))
    changed = set()
    for item in files:
        filename = str(item.get('filename', ''))
        status = str(item.get('status', ''))
        if not filename or status == 'removed':
            raise HandoffError('evidence transition PR contains a removed/invalid file')
        changed.add(filename)
    if not changed or not changed.issubset(allowed):
        raise HandoffError(f'evidence transition PR changed files outside the {allow_name} allowlist: {sorted(changed - allowed)}')
    if not required.issubset(changed):
        raise HandoffError(f'evidence transition PR is missing required paths: {sorted(required - changed)}')
    return {'prNumber': int(pr_number), 'mergeCommitSha': merge_sha, 'changedPaths': sorted(changed), 'allowlist': allow_name}


def git_output(*args: str) -> str:
    proc = subprocess.run(['git', *args], cwd=ROOT, text=True, capture_output=True)
    if proc.returncode != 0:
        raise HandoffError(f'git {" ".join(args)} failed')
    return proc.stdout.strip()


def changed_paths() -> set[str]:
    out = git_output('status', '--porcelain=v1', '--untracked-files=all')
    paths: set[str] = set()
    for line in out.splitlines():
        if not line:
            continue
        raw = line[3:]
        if ' -> ' in raw:
            raise HandoffError('renamed files are not allowed in local evidence promotion')
        paths.add(raw)
    return paths


def verify_local_promotion(stage: str, ledger: dict[str, Any], contract: dict[str, Any]) -> list[str]:
    hint = contract['firstRealRun']['stageLaunchHints'].get(stage) or {}
    if hint.get('kind') != 'local-source-transition-preparation':
        raise HandoffError(f'{stage} is not a local source-transition preparation stage')
    if git_output('branch', '--show-current') != ledger['defaultBranch']:
        raise HandoffError('local evidence promotion must start from the default branch checkout')
    if git_output('rev-parse', 'HEAD').lower() != ledger['currentSourceHeadSha']:
        raise HandoffError('local evidence promotion checkout HEAD does not match the ledger source commit')
    allow_name = str(hint.get('allowlist', ''))
    allow_cfg = contract['firstRealRun']['sourceTransitionAllowlists'][allow_name]
    allowed = set(allow_cfg['paths'])
    required = set(allow_cfg['requiredPaths'])
    changed = changed_paths()
    if not changed or not changed.issubset(allowed):
        raise HandoffError(f'local evidence promotion changed files outside {allow_name}: {sorted(changed - allowed)}')
    if not required.issubset(changed):
        raise HandoffError(f'local evidence promotion is missing required paths: {sorted(required - changed)}')
    proc = subprocess.run([os.fspath(ROOT / 'scripts' / 'verify_source_integrity.py')], cwd=ROOT, text=True, capture_output=True)
    if proc.returncode != 0:
        # Execute through the active Python if the script is not directly executable.
        proc = subprocess.run([os.sys.executable, os.fspath(ROOT / 'scripts' / 'verify_source_integrity.py')], cwd=ROOT, text=True, capture_output=True)
    if proc.returncode != 0:
        raise HandoffError('local evidence promotion does not satisfy Source Integrity')
    return sorted(changed)


def load_recovery_module():
    spec = importlib.util.spec_from_file_location('mte_first_real_run_recovery_handoff', RECOVERY_TOOL)
    if spec is None or spec.loader is None:
        raise HandoffError('could not load first-real-run recovery module')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_manual_checkpoint_module():
    path = ROOT / 'scripts' / 'manual_boundary_checkpoint.py'
    spec = importlib.util.spec_from_file_location('mte_manual_checkpoint_for_handoff', path)
    if spec is None or spec.loader is None:
        raise HandoffError('could not load manual boundary checkpoint validator')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_manual_checkpoint_record(stage: str, checkpoint_path: Path, evidence_items: list[str], ledger: dict[str, Any], contract: dict[str, Any], token: str | None, actor_snapshot: Path | None) -> dict[str, Any]:
    module = load_manual_checkpoint_module()
    value = json.loads(checkpoint_path.resolve().read_text(encoding='utf-8'))
    try:
        module.validate_checkpoint(value, stage=stage, ledger=ledger)
        evidence = module.parse_evidence(evidence_items)
        module.validate_checkpoint_evidence(value, evidence, ledger=ledger)
    except Exception as exc:
        raise HandoffError(f'manual checkpoint/evidence is invalid: {exc}') from exc
    try:
        actor, live_head = module.operator_and_head(ledger['repository'], ledger['defaultBranch'], token, actor_snapshot, contract['githubInfrastructureAudit']['apiVersion'], ledger['repositoryId'])
    except Exception as exc:
        raise HandoffError(f'could not re-verify manual checkpoint operator/source identity: {exc}') from exc
    checkpoint_actor = value.get('operator') if isinstance(value.get('operator'), dict) else {}
    if actor.get('id') != str(checkpoint_actor.get('id')):
        raise HandoffError('current authenticated GitHub operator differs from the operator that created the manual checkpoint')
    if actor.get('id') not in {str(x) for x in ledger['authorizedOperatorIds']}:
        raise HandoffError('manual checkpoint operator is not in the sealed production operator allowlist')
    if live_head != ledger['currentSourceHeadSha']:
        raise HandoffError('default branch moved after the manual checkpoint; recreate/review it against the current source commit')
    return value


def append_record(ledger: dict[str, Any], stage: str, **fields: Any) -> None:
    record = {
        'stage': stage,
        'status': 'success',
        'recordedAt': now_iso(),
        'sourceHeadShaBefore': ledger['currentSourceHeadSha'],
        'manualReviewed': bool(fields.pop('manualReviewed', False)),
        **fields,
    }
    ledger['records'].append(record)


def main() -> int:
    parser = argparse.ArgumentParser(description='Commit-aware operator handoff ledger for the first real production run. Operational state only; not release evidence.')
    parser.add_argument('--contract', type=Path, default=DEFAULT_CONTRACT)
    sub = parser.add_subparsers(dest='command', required=True)

    p = sub.add_parser('init')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--release-id', required=True)
    p.add_argument('--release-class', choices=['private-v1', 'public-v1'], required=True)
    p.add_argument('--onboarding-config', type=Path, required=True)

    p = sub.add_parser('record')
    p.add_argument('--ledger', type=Path, required=True)
    p.add_argument('--stage', required=True)
    p.add_argument('--manual-reviewed', action='store_true')
    p.add_argument('--note')

    p = sub.add_parser('record-manual')
    p.add_argument('--ledger', type=Path, required=True)
    p.add_argument('--stage', required=True)
    p.add_argument('--checkpoint', type=Path, required=True)
    p.add_argument('--evidence', action='append', default=[], help='Repeat the same role=path evidence set used to create the checkpoint; bytes are revalidated before recording.')
    p.add_argument('--token-env', default='MTE_PRODUCTION_CONTROLLER_TOKEN')
    p.add_argument('--actor-snapshot', type=Path, help='Tests/offline validation only; live production recording requires the authenticated operator token.')
    p.add_argument('--note')
    p.add_argument('--recovery-root', type=Path)

    p = sub.add_parser('record-run')
    p.add_argument('--ledger', type=Path, required=True)
    p.add_argument('--stage', required=True)
    p.add_argument('--run-id', action='append', required=True)
    p.add_argument('--snapshot-dir', type=Path)
    p.add_argument('--pr-created-snapshot', type=Path, help='Offline/test snapshot for a workflow-created evidence PR; live verification discovers the PR by its sealed branch.')
    p.add_argument('--intent-nonce', required=True)
    p.add_argument('--token-env', default='MTE_INFRA_PROVISION_TOKEN')
    p.add_argument('--note')
    p.add_argument('--recovery-root', type=Path)

    p = sub.add_parser('record-pr-merge')
    p.add_argument('--ledger', type=Path, required=True)
    p.add_argument('--stage', required=True)
    p.add_argument('--pr-number', type=int, required=True)
    p.add_argument('--snapshot', type=Path)
    p.add_argument('--token-env', default='MTE_INFRA_PROVISION_TOKEN')
    p.add_argument('--note')

    p = sub.add_parser('status')
    p.add_argument('--ledger', type=Path, required=True)

    args = parser.parse_args()
    contract_path = args.contract.resolve()
    contract = load_contract(contract_path)

    if args.command == 'init':
        onboarding_path = args.onboarding_config.resolve()
        onboarding = load_bound_onboarding(onboarding_path, contract, contract_path)
        binding = onboarding['repositoryBinding']
        ledger = {
            'schemaVersion': 4,
            'revision': LEDGER_REVISION,
            'releaseId': args.release_id,
            'releaseClass': args.release_class,
            'repository': onboarding['repository'],
            'repositoryId': binding['repositoryId'],
            'defaultBranch': binding['defaultBranch'],
            'initialSourceHeadSha': binding['defaultBranchHeadSha'],
            'currentSourceHeadSha': binding['defaultBranchHeadSha'],
            'workflowSetSha256': binding['workflowSetSha256'],
            'onboardingConfigSha256': onboarding['configSha256'],
            'authorizedOperatorIds': [str(x['id']) for x in binding['authorizedOperators']],
            'authorizedOperatorLogins': [str(x['login']) for x in binding['authorizedOperators']],
            'contractSha256': file_sha256(contract_path),
            'createdAt': now_iso(),
            'records': [],
            'notice': 'Operational handoff only; run and merged-PR provenance is verified before recording. This file is not qualification, smoke, signing, or release evidence.',
        }
        write(args.output, ledger)
        first = next_stage(ledger, contract)
        print(json.dumps({'passed': True, 'repository': ledger['repository'], 'repositoryId': ledger['repositoryId'], 'currentSourceHeadSha': ledger['currentSourceHeadSha'], 'authorizedOperatorIds': ledger['authorizedOperatorIds'], 'authorizedOperatorLogins': ledger['authorizedOperatorLogins'], 'nextStage': first, 'nextStageLaunch': stage_hint(first, contract), 'ledger': str(args.output)}, indent=2))
        return 0

    ledger = json.loads(args.ledger.read_text(encoding='utf-8'))
    validate(ledger, contract, contract_path)

    if args.command == 'status':
        nxt = next_stage(ledger, contract)
        print(json.dumps({'passed': True, 'repository': ledger['repository'], 'currentSourceHeadSha': ledger['currentSourceHeadSha'], 'completedStageCount': len(ledger['records']), 'stageCount': len(stage_plan(ledger, contract)), 'nextStage': nxt, 'nextStageLaunch': stage_hint(nxt, contract), 'complete': nxt is None}, indent=2))
        return 0

    expected = next_stage(ledger, contract)
    if expected is None:
        raise HandoffError('first real run ledger is already complete')
    if args.stage != expected:
        raise HandoffError(f'next stage must be {expected}, not {args.stage}')
    hint = contract['firstRealRun']['stageLaunchHints'].get(args.stage) or {}

    if args.command == 'record-run':
        token = None if args.snapshot_dir else os.environ.get(args.token_env, '').strip()
        nonce = str(args.intent_nonce)
        if not nonce.startswith('mte-') or len(nonce) < 12:
            raise HandoffError('intent nonce must use the mte- prefix and contain sufficient entropy')
        observations = verify_run_stage(args.stage, [str(x) for x in args.run_id], ledger, contract, token, args.snapshot_dir, expected_nonce=nonce)
        fields: dict[str, Any] = {'runIntentNonce': nonce, 'runObservations': observations, 'note': args.note}
        recovery = load_recovery_module()
        minimum = int(((contract['firstRealRun'].get('recovery') or {}).get('minimumArtifactsByStage') or {}).get(args.stage, 0))
        if args.snapshot_dir:
            fields['recoverySnapshot'] = recovery.capture_offline_test_stage(ledger=ledger, stage=args.stage, observations=observations, snapshot_dir=args.snapshot_dir, root=args.recovery_root)
        else:
            try:
                fields['recoverySnapshot'] = recovery.capture_automated_stage(ledger=ledger, stage=args.stage, observations=observations, token=token, version=contract['githubInfrastructureAudit']['apiVersion'], root=args.recovery_root, minimum_artifacts=minimum)
            except Exception as exc:
                raise HandoffError(f'disaster-recovery capture failed before run recording: {exc}') from exc
        if created_pr_config(args.stage, contract):
            pr_token = None if args.pr_created_snapshot else (token or os.environ.get('MTE_PRODUCTION_CONTROLLER_TOKEN', '').strip())
            fields['pullRequestCreated'] = verify_created_pr_stage(args.stage, nonce, ledger, contract, pr_token, args.pr_created_snapshot)
        append_record(ledger, args.stage, **fields)
    elif args.command == 'record-manual':
        if args.stage not in contract['firstRealRun'].get('manualReviewBoundaries', []):
            raise HandoffError(f'{args.stage} is not a manual review boundary')
        token = None if args.actor_snapshot else os.environ.get(args.token_env, '').strip()
        if args.actor_snapshot is None and not token:
            raise HandoffError(f'{args.token_env} is required to re-verify the authorized GitHub operator for a live manual checkpoint')
        checkpoint = verify_manual_checkpoint_record(args.stage, args.checkpoint, args.evidence, ledger, contract, token, args.actor_snapshot)
        manual_module = load_manual_checkpoint_module()
        evidence_paths = manual_module.parse_evidence(args.evidence)
        recovery = load_recovery_module()
        try:
            recovery_snapshot = recovery.capture_manual_stage(ledger=ledger, stage=args.stage, checkpoint_path=args.checkpoint, evidence=evidence_paths, root=args.recovery_root)
        except Exception as exc:
            raise HandoffError(f'disaster-recovery capture failed before manual checkpoint recording: {exc}') from exc
        append_record(ledger, args.stage, manualReviewed=True, manualCheckpoint=checkpoint, recoverySnapshot=recovery_snapshot, note=args.note)
    elif args.command == 'record-pr-merge':
        token = None if args.snapshot else os.environ.get(args.token_env, '').strip()
        transition = verify_pr_transition(args.stage, args.pr_number, ledger, contract, token, args.snapshot)
        before = ledger['currentSourceHeadSha']
        ledger['currentSourceHeadSha'] = transition['mergeCommitSha']
        append_record(ledger, args.stage, sourceHeadShaBefore=before, sourceHeadShaAfter=transition['mergeCommitSha'], pullRequest=transition, note=args.note)
        # append_record uses currentSourceHeadSha, so repair the explicit before value after the transition update.
        ledger['records'][-1]['sourceHeadShaBefore'] = before
    else:
        kind = hint.get('kind')
        if kind in {'workflow', 'workflow-set', 'merged-pr-transition', 'evidence-pr-created', 'local-checkout-reconciliation'}:
            raise HandoffError(f'{args.stage} must be recorded with record-run or record-pr-merge, not record')
        manual_required = args.stage in contract['firstRealRun'].get('manualReviewBoundaries', [])
        if manual_required:
            raise HandoffError(f'{args.stage} must be recorded with record-manual and a verified content-addressed checkpoint; --manual-reviewed alone is not accepted')
        fields: dict[str, Any] = {'manualReviewed': False}
        if kind == 'local-source-transition-preparation':
            raise HandoffError(f'{args.stage} must be advanced with first_real_run_controller.py so the verified local promotion and exact PR creation are recorded atomically')
        if args.note:
            fields['note'] = args.note
        append_record(ledger, args.stage, **fields)

    write(args.ledger, ledger)
    # Re-read and validate to prove the persisted chain is internally coherent.
    persisted = json.loads(args.ledger.read_text(encoding='utf-8'))
    validate(persisted, contract, contract_path)
    nxt = next_stage(persisted, contract)
    print(json.dumps({'passed': True, 'recordedStage': args.stage, 'currentSourceHeadSha': persisted['currentSourceHeadSha'], 'nextStage': nxt, 'nextStageLaunch': stage_hint(nxt, contract)}, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except HandoffError as exc:
        print(json.dumps({'passed': False, 'error': str(exc)}, indent=2))
        raise SystemExit(2)
