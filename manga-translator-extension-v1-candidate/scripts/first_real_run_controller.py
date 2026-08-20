from __future__ import annotations

import argparse
import importlib.util
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HANDOFF_TOOL = ROOT / 'scripts' / 'first_real_run_handoff.py'
EVIDENCE_PR_TOOL = ROOT / 'scripts' / 'evidence_transition_pr.py'
RECONCILE_TOOL = ROOT / 'scripts' / 'reconcile_first_real_run_checkout.py'
RECOVERY_TOOL = ROOT / 'scripts' / 'first_real_run_recovery.py'
DEFAULT_CONTRACT = ROOT / 'release-control' / 'production-execution-contract.json'
CONTROLLER_REVISION = 'rev32-first-real-run-controller-v5'


class ControllerError(ValueError):
    pass


def load_handoff():
    spec = importlib.util.spec_from_file_location('mte_first_real_run_handoff_controller', HANDOFF_TOOL)
    if spec is None or spec.loader is None:
        raise ControllerError('could not load first-real-run handoff module')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


H = load_handoff()


def load_evidence_pr():
    spec = importlib.util.spec_from_file_location('mte_evidence_pr_for_controller', EVIDENCE_PR_TOOL)
    if spec is None or spec.loader is None:
        raise ControllerError('could not load evidence transition PR module')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


E = load_evidence_pr()


def load_reconcile():
    spec = importlib.util.spec_from_file_location('mte_checkout_reconcile_for_controller', RECONCILE_TOOL)
    if spec is None or spec.loader is None:
        raise ControllerError('could not load checkout reconciliation module')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = load_reconcile()


def load_recovery():
    spec = importlib.util.spec_from_file_location('mte_first_real_run_recovery_controller', RECOVERY_TOOL)
    if spec is None or spec.loader is None:
        raise ControllerError('could not load first-real-run recovery module')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


D = load_recovery()


def api_request(method: str, url: str, token: str, api_version: str, payload: Any | None = None) -> tuple[int, Any | None]:
    data = None if payload is None else json.dumps(payload, separators=(',', ':')).encode('utf-8')
    req = urllib.request.Request(url, data=data, method=method, headers={
        'Accept': 'application/vnd.github+json',
        'Authorization': f'Bearer {token}',
        'X-GitHub-Api-Version': api_version,
        'User-Agent': 'mte-first-real-run-controller',
        'Content-Type': 'application/json',
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            return response.status, (json.loads(raw.decode('utf-8')) if raw else None)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')[:800]
        raise ControllerError(f'GitHub API {method} {url} failed with HTTP {exc.code}: {body}') from exc
    except urllib.error.URLError as exc:
        raise ControllerError(f'GitHub API {method} {url} failed: {exc.reason}') from exc


def api_get(url: str, token: str, version: str) -> Any:
    status, payload = api_request('GET', url, token, version)
    if status != 200:
        raise ControllerError(f'unexpected GitHub GET status {status}')
    return payload


def repo_base(ledger: dict[str, Any]) -> str:
    owner, repo = str(ledger['repository']).split('/', 1)
    return f'https://api.github.com/repos/{urllib.parse.quote(owner, safe="")}/{urllib.parse.quote(repo, safe="")}'


def workflow_id(path: str) -> str:
    return urllib.parse.quote(Path(path).name, safe='')


def assert_live_default_branch_head(ledger: dict[str, Any], token: str, version: str) -> None:
    base = repo_base(ledger)
    meta = api_get(base, token, version)
    if str(meta.get('id', '')) != str(ledger.get('repositoryId', '')):
        raise ControllerError('live repository id differs from the sealed onboarding/ledger repository identity')
    if str(meta.get('default_branch', '')) != str(ledger['defaultBranch']):
        raise ControllerError('live repository default branch differs from the sealed onboarding/ledger default branch')
    branch = urllib.parse.quote(str(ledger['defaultBranch']), safe='')
    payload = api_get(f'{base}/branches/{branch}', token, version)
    sha = str(((payload or {}).get('commit') or {}).get('sha', '')).lower()
    if sha != str(ledger['currentSourceHeadSha']).lower():
        raise ControllerError(f'default branch moved: live={sha or "missing"} ledger={ledger["currentSourceHeadSha"]}; verify/record the source transition before dispatching')


def assert_live_default_branch_is(ledger: dict[str, Any], expected_sha: str, token: str, version: str) -> None:
    base = repo_base(ledger)
    meta = api_get(base, token, version)
    if str(meta.get('id', '')) != str(ledger.get('repositoryId', '')) or str(meta.get('default_branch', '')) != str(ledger['defaultBranch']):
        raise ControllerError('live repository identity/default branch differs from the sealed ledger')
    branch = urllib.parse.quote(str(ledger['defaultBranch']), safe='')
    payload = api_get(f'{base}/branches/{branch}', token, version)
    sha = str(((payload or {}).get('commit') or {}).get('sha', '')).lower()
    if sha != expected_sha.lower():
        raise ControllerError(f'default branch HEAD is {sha or "missing"}, expected exact evidence merge commit {expected_sha}; another commit landed before the ledger transition was recorded')


def parse_inputs(items: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in items:
        if '=' not in item:
            raise ControllerError(f'--input must be KEY=VALUE, got {item!r}')
        key, value = item.split('=', 1)
        key = key.strip()
        if not key or key == 'run_intent_nonce':
            raise ControllerError('run_intent_nonce is controller-owned and cannot be supplied manually')
        if key in out:
            raise ControllerError(f'duplicate --input key: {key}')
        out[key] = value
    return out


def stage_record(ledger: dict[str, Any], stage: str) -> dict[str, Any]:
    for record in ledger.get('records') or []:
        if record.get('stage') == stage:
            return record
    raise ControllerError(f'ledger has no completed record for required stage {stage}')


def run_id_from_stage(ledger: dict[str, Any], stage: str, workflow: str | None = None) -> str:
    record = stage_record(ledger, stage)
    observations = record.get('runObservations') or []
    if workflow is None:
        if len(observations) != 1:
            raise ControllerError(f'{stage} does not contain exactly one run observation')
        return str(observations[0]['runId'])
    for obs in observations:
        if obs.get('workflow') == workflow:
            return str(obs['runId'])
    raise ControllerError(f'{stage} has no run observation for {workflow}')


def derive_value(spec: str, ledger: dict[str, Any]) -> Any:
    if spec == '$releaseId':
        return ledger['releaseId']
    if spec == '$releaseClass':
        return ledger['releaseClass']
    if spec == '$releaseClassIsPublic':
        return ledger['releaseClass'] == 'public-v1'
    if '.controllerInput:' in spec:
        stage, key = spec.split('.controllerInput:', 1)
        value = (stage_record(ledger, stage).get('controllerInputs') or {}).get(key)
        if value in (None, ''):
            raise ControllerError(f'{stage} has no persisted controller input {key!r}')
        return value
    if spec.endswith('.runId') and ':' not in spec:
        return run_id_from_stage(ledger, spec[:-6])
    if spec.endswith('.runId(public-v1-only)'):
        if ledger['releaseClass'] != 'public-v1':
            return None
        return run_id_from_stage(ledger, spec[:-22])
    if ':' in spec:
        stage, workflow = spec.split(':', 1)
        return run_id_from_stage(ledger, stage, workflow)
    raise ControllerError(f'unsupported controller-derived input expression: {spec}')


def resolve_dispatches(stage: str, ledger: dict[str, Any], contract: dict[str, Any], operator_inputs: dict[str, Any], nonce: str) -> list[dict[str, Any]]:
    hint = contract['firstRealRun']['stageLaunchHints'].get(stage) or {}
    kind = hint.get('kind')
    if kind not in {'workflow', 'workflow-set'}:
        raise ControllerError(f'{stage} is not controller-dispatchable')
    allowed = set(hint.get('controllerRequiredInputs') or [])
    unknown = sorted(set(operator_inputs) - allowed)
    if unknown:
        raise ControllerError(f'unexpected controller input(s) for {stage}: {unknown}')
    missing = sorted(k for k in allowed if not str(operator_inputs.get(k, '')).strip())
    if missing:
        raise ControllerError(f'{stage} requires controller input(s): {missing}')

    common: dict[str, Any] = {}
    common.update(hint.get('controllerFixedInputs') or {})
    common.update(operator_inputs)
    for key, spec in (hint.get('controllerDerivedInputs') or {}).items():
        value = derive_value(str(spec), ledger)
        if value is not None:
            common[key] = value
    common['run_intent_nonce'] = nonce

    workflows = [hint['workflow']] if kind == 'workflow' else list(hint.get('workflows') or [])
    per = hint.get('controllerPerWorkflowInputs') or {}
    dispatches = []
    for workflow in workflows:
        inputs = dict(common)
        for key, value in (per.get(workflow) or {}).items():
            inputs[key] = derive_value(value, ledger) if isinstance(value, str) and value.startswith('$') else value
        dispatches.append({'workflow': workflow, 'inputs': inputs, 'runId': None})
    return dispatches


def dispatch_workflow(ledger: dict[str, Any], workflow: str, inputs: dict[str, Any], token: str, version: str) -> str | None:
    url = f'{repo_base(ledger)}/actions/workflows/{workflow_id(workflow)}/dispatches'
    status, payload = api_request('POST', url, token, version, {'ref': ledger['defaultBranch'], 'inputs': inputs})
    if status not in {200, 204}:
        raise ControllerError(f'unexpected workflow dispatch status {status}')
    if isinstance(payload, dict) and payload.get('workflow_run_id') is not None:
        return str(payload['workflow_run_id'])
    return None


def recover_run_by_nonce(ledger: dict[str, Any], workflow: str, nonce: str, token: str, version: str) -> str | None:
    query = urllib.parse.urlencode({
        'branch': ledger['defaultBranch'],
        'event': 'workflow_dispatch',
        'head_sha': ledger['currentSourceHeadSha'],
        'per_page': 100,
    })
    payload = api_get(f'{repo_base(ledger)}/actions/workflows/{workflow_id(workflow)}/runs?{query}', token, version)
    candidates = []
    for run in (payload or {}).get('workflow_runs') or []:
        if nonce not in str(run.get('display_title') or ''):
            continue
        if str(run.get('head_sha', '')).lower() != ledger['currentSourceHeadSha']:
            continue
        if str(run.get('head_branch', '')) != ledger['defaultBranch']:
            continue
        candidates.append(str(run.get('id')))
    candidates = sorted(set(x for x in candidates if x and x != 'None'))
    if len(candidates) > 1:
        raise ControllerError(f'multiple workflow runs match pending intent {nonce} for {workflow}: {candidates}')
    return candidates[0] if candidates else None


def get_run(ledger: dict[str, Any], run_id: str, token: str, version: str) -> dict[str, Any]:
    payload = api_get(f'{repo_base(ledger)}/actions/runs/{urllib.parse.quote(str(run_id), safe="")}', token, version)
    if not isinstance(payload, dict):
        raise ControllerError(f'workflow run {run_id} response is invalid')
    return payload


def wait_for_run(ledger: dict[str, Any], run_id: str, token: str, version: str, poll_seconds: float, timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_status = None
    while True:
        run = get_run(ledger, run_id, token, version)
        status = str(run.get('status') or '')
        if status != last_status:
            print(json.dumps({'controllerEvent': 'run-status', 'runId': str(run_id), 'status': status, 'conclusion': run.get('conclusion')}, separators=(',', ':')), file=sys.stderr)
            last_status = status
        if status == 'completed':
            return run
        if time.monotonic() >= deadline:
            raise ControllerError(f'timed out waiting for workflow run {run_id}; pending launch remains sealed for resume')
        time.sleep(max(0.05, poll_seconds))


def write_and_validate(path: Path, ledger: dict[str, Any], contract: dict[str, Any], contract_path: Path) -> None:
    H.write(path, ledger)
    persisted = json.loads(path.read_text(encoding='utf-8'))
    H.validate(persisted, contract, contract_path)


def create_pending(stage: str, ledger: dict[str, Any], contract: dict[str, Any], operator_inputs: dict[str, Any]) -> dict[str, Any]:
    nonce = 'mte-' + secrets.token_hex(16)
    return {
        'revision': CONTROLLER_REVISION,
        'stage': stage,
        'sourceHeadSha': ledger['currentSourceHeadSha'],
        'runIntentNonce': nonce,
        'createdAt': H.now_iso(),
        'operatorInputs': operator_inputs,
        'dispatches': resolve_dispatches(stage, ledger, contract, operator_inputs, nonce),
    }


def automated_kind(stage: str, contract: dict[str, Any]) -> bool:
    return (contract['firstRealRun']['stageLaunchHints'].get(stage) or {}).get('kind') in {'workflow', 'workflow-set'}


def boundary_result(stage: str, ledger: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    hint = H.stage_hint(stage, contract)
    result = {
        'passed': True,
        'advanced': False,
        'blocked': True,
        'stage': stage,
        'kind': (hint or {}).get('kind') if isinstance(hint, dict) else None,
        'currentSourceHeadSha': ledger['currentSourceHeadSha'],
        'nextAction': hint,
        'message': 'This boundary is intentionally not auto-completed by the controller.',
    }
    if stage in contract['firstRealRun'].get('manualReviewBoundaries', []):
        roles = list((hint or {}).get('checkpointEvidenceRoles') or []) if isinstance(hint, dict) else []
        result['manualCheckpoint'] = {
            'tool': 'scripts/manual_boundary_checkpoint.py',
            'requiredEvidenceRoles': roles,
            'createExample': 'python scripts/manual_boundary_checkpoint.py --stage ' + stage + ' --ledger <ledger.json> ' + ' '.join(f'--evidence {role}=<path>' for role in roles) + ' --output <checkpoint.json>',
            'recordExample': 'python scripts/first_real_run_handoff.py record-manual --ledger <ledger.json> --stage ' + stage + ' --checkpoint <checkpoint.json> ' + ' '.join(f'--evidence {role}=<path>' for role in roles),
        }
        result['message'] += ' Complete the human review, create a content-addressed manual checkpoint, then record that checkpoint; a boolean approval flag is not accepted.'
    else:
        result['message'] += ' Complete the external/local transition and record it with first_real_run_handoff.py.'
    return result


def record_verified_stage(ledger: dict[str, Any], stage: str, nonce: str, observations: list[dict[str, Any]], contract: dict[str, Any], operator_inputs: dict[str, Any] | None = None, pull_request_created: dict[str, Any] | None = None, recovery_snapshot: dict[str, Any] | None = None) -> list[str]:
    completed = []
    fields: dict[str, Any] = {'runIntentNonce': nonce, 'runObservations': observations, 'controllerInputs': dict(operator_inputs or {}), 'controllerRevision': CONTROLLER_REVISION}
    if pull_request_created is not None:
        fields['pullRequestCreated'] = pull_request_created
    if recovery_snapshot is None:
        raise ControllerError(f'{stage} cannot be recorded before its disaster-recovery snapshot is sealed')
    fields['recoverySnapshot'] = recovery_snapshot
    H.append_record(ledger, stage, **fields)
    completed.append(stage)
    for extra in (contract['firstRealRun']['stageLaunchHints'].get(stage) or {}).get('alsoSatisfiesNextStages') or []:
        if H.next_stage(ledger, contract) != extra:
            raise ControllerError(f'controller reuse contract drift: expected next stage {extra}')
        H.append_record(ledger, extra, runIntentNonce=nonce, runObservations=observations, reusedControllerRunFrom=stage, recoverySnapshotRef={'stage': stage, 'manifestSha256': recovery_snapshot['manifestSha256']}, controllerRevision=CONTROLLER_REVISION)
        completed.append(extra)
    return completed


def reuse_previous_run_if_configured(path: Path, ledger: dict[str, Any], stage: str, contract: dict[str, Any], contract_path: Path, token: str, version: str) -> dict[str, Any] | None:
    hint = contract['firstRealRun']['stageLaunchHints'].get(stage) or {}
    previous = hint.get('reuseRunFromStage')
    if not previous:
        return None
    record = stage_record(ledger, str(previous))
    nonce = str(record.get('runIntentNonce', ''))
    run_ids = [str(obs['runId']) for obs in record.get('runObservations') or []]
    observations = H.verify_run_stage(stage, run_ids, ledger, contract, token, None, expected_nonce=nonce)
    source_recovery = record.get('recoverySnapshot')
    if not isinstance(source_recovery, dict):
        raise ControllerError(f'{previous} has no sealed recovery snapshot to reuse')
    try:
        D.verify_summary(source_recovery, stage=str(previous), expected_run_ids=run_ids, source_head_sha=str(record.get('sourceHeadShaBefore', '')))
    except Exception as exc:
        raise ControllerError(f'{previous} recovery snapshot is missing/corrupt: {exc}') from exc
    H.append_record(ledger, stage, runIntentNonce=nonce, runObservations=observations, reusedControllerRunFrom=previous, recoverySnapshotRef={'stage': previous, 'manifestSha256': source_recovery['manifestSha256']}, controllerRevision=CONTROLLER_REVISION)
    write_and_validate(path, ledger, contract, contract_path)
    return {'passed': True, 'advanced': True, 'recordedStages': [stage], 'reusedRunIds': run_ids, 'nextStage': H.next_stage(ledger, contract)}


def advance_local_evidence_pr(path: Path, ledger: dict[str, Any], stage: str, contract: dict[str, Any], contract_path: Path, token: str, version: str) -> dict[str, Any]:
    hint = contract['firstRealRun']['stageLaunchHints'].get(stage) or {}
    created_stage = str(hint.get('prCreatedStage', ''))
    if not created_stage or H.next_stage(ledger, contract) != stage:
        raise ControllerError('local evidence PR stage contract is invalid')
    assert_live_default_branch_head(ledger, token, version)
    pending = ledger.get('pendingEvidencePr')
    if pending is None:
        nonce = 'mte-pr-' + secrets.token_hex(16)
        try:
            pending = E.pending_snapshot(stage, ledger, contract, nonce)
        except Exception as exc:
            raise ControllerError(f'local evidence promotion is not ready for PR creation: {exc}') from exc
        ledger['pendingEvidencePr'] = pending
        write_and_validate(path, ledger, contract, contract_path)
        ledger = json.loads(path.read_text(encoding='utf-8'))
        pending = ledger['pendingEvidencePr']
    else:
        try:
            E.validate_pending(pending, stage, ledger, contract)
        except Exception as exc:
            raise ControllerError(f'pending evidence PR is stale or local promotion bytes changed: {exc}') from exc
    try:
        created = E.create_or_recover(ledger=ledger, stage=stage, pending=pending, contract=contract, token=token, version=version)
    except Exception as exc:
        raise ControllerError(f'evidence PR creation/recovery failed; pending plan remains sealed: {exc}') from exc
    # Re-check local bytes after the remote mutation before committing ledger state.
    E.validate_pending(pending, stage, ledger, contract)
    H.append_record(ledger, stage, changedPaths=list(pending['changedPaths']), changedFiles=dict(pending['files']), prIntentNonce=pending['prIntentNonce'], controllerRevision=CONTROLLER_REVISION)
    if H.next_stage(ledger, contract) != created_stage:
        raise ControllerError(f'controller contract drift: expected PR-created stage {created_stage}')
    H.append_record(ledger, created_stage, pullRequestCreated=created, prIntentNonce=pending['prIntentNonce'], controllerRevision=CONTROLLER_REVISION)
    ledger.pop('pendingEvidencePr', None)
    write_and_validate(path, ledger, contract, contract_path)
    return {'passed': True, 'advanced': True, 'recordedStages': [stage, created_stage], 'pullRequest': created, 'nextStage': H.next_stage(ledger, contract), 'nextStageLaunch': H.stage_hint(H.next_stage(ledger, contract), contract)}


def advance_checkout_reconciliation(path: Path, ledger: dict[str, Any], stage: str, contract: dict[str, Any], contract_path: Path, token: str, version: str) -> dict[str, Any]:
    hint = contract['firstRealRun']['stageLaunchHints'].get(stage) or {}
    merge_stage = str(hint.get('mergeStage', ''))
    if not merge_stage:
        raise ControllerError('checkout reconciliation stage does not declare its mergeStage')
    merge_record = stage_record(ledger, merge_stage)
    assert_live_default_branch_head(ledger, token, version)
    try:
        result = R.reconcile_checkout(repo_root=ROOT, ledger=ledger, merge_record=merge_record)
    except Exception as exc:
        raise ControllerError(f'local checkout reconciliation failed closed: {exc}') from exc
    H.append_record(ledger, stage, checkoutReconciliation=result, controllerRevision=CONTROLLER_REVISION)
    write_and_validate(path, ledger, contract, contract_path)
    return {'passed': True, 'advanced': True, 'recordedStages': [stage], 'checkoutReconciliation': result, 'nextStage': H.next_stage(ledger, contract), 'nextStageLaunch': H.stage_hint(H.next_stage(ledger, contract), contract)}


def advance_merged_pr(path: Path, ledger: dict[str, Any], stage: str, contract: dict[str, Any], contract_path: Path, token: str, version: str) -> dict[str, Any]:
    hint = contract['firstRealRun']['stageLaunchHints'].get(stage) or {}
    created_stage = str(hint.get('prCreatedStage', ''))
    if not created_stage:
        raise ControllerError('merged-PR stage does not declare its PR-created stage')
    created_record = stage_record(ledger, created_stage)
    created = created_record.get('pullRequestCreated') if isinstance(created_record.get('pullRequestCreated'), dict) else None
    if not created:
        raise ControllerError('ledger does not contain the pull request identity that must be reviewed/merged')
    pr_number = int(created.get('prNumber', 0))
    obs = H.load_pr_observation(pr_number, ledger, contract, token, None)
    pr = obs.get('pullRequest') or {}
    if not pr.get('merged_at'):
        return {'passed': True, 'advanced': False, 'blocked': True, 'stage': stage, 'kind': 'merged-pr-transition', 'pullRequest': created, 'message': 'The exact recorded evidence PR is awaiting human review/merge. Merge this PR without changing its head, then run controller advance/resume again.'}
    transition = H.verify_pr_transition(stage, pr_number, ledger, contract, token, None, observation=obs)
    assert_live_default_branch_is(ledger, transition['mergeCommitSha'], token, version)
    before = ledger['currentSourceHeadSha']
    ledger['currentSourceHeadSha'] = transition['mergeCommitSha']
    H.append_record(ledger, stage, sourceHeadShaBefore=before, sourceHeadShaAfter=transition['mergeCommitSha'], pullRequest=transition, controllerRevision=CONTROLLER_REVISION)
    ledger['records'][-1]['sourceHeadShaBefore'] = before
    write_and_validate(path, ledger, contract, contract_path)
    return {'passed': True, 'advanced': True, 'recordedStages': [stage], 'pullRequest': transition, 'currentSourceHeadSha': ledger['currentSourceHeadSha'], 'nextStage': H.next_stage(ledger, contract), 'nextStageLaunch': H.stage_hint(H.next_stage(ledger, contract), contract)}


def assert_recovery_chain(ledger: dict[str, Any], contract: dict[str, Any]) -> None:
    try:
        D.verify_ledger_recovery(ledger, contract)
    except Exception as exc:
        raise ControllerError(f'first-real-run recovery chain is missing/corrupt; restore the content-addressed recovery snapshot before continuing: {exc}') from exc


def capture_recovery(stage: str, ledger: dict[str, Any], observations: list[dict[str, Any]], contract: dict[str, Any], token: str, version: str) -> dict[str, Any]:
    cfg = contract['firstRealRun'].get('recovery') or {}
    minimum = int((cfg.get('minimumArtifactsByStage') or {}).get(stage, 0))
    try:
        return D.capture_automated_stage(ledger=ledger, stage=stage, observations=observations, token=token, version=version, minimum_artifacts=minimum)
    except Exception as exc:
        raise ControllerError(f'disaster-recovery capture failed for {stage}; successful workflow runs are not committed to the ledger until recovery bytes are sealed: {exc}') from exc


def advance(path: Path, contract: dict[str, Any], contract_path: Path, token: str, operator_inputs: dict[str, Any], poll_seconds: float, timeout_seconds: float) -> dict[str, Any]:
    ledger = json.loads(path.read_text(encoding='utf-8'))
    H.validate(ledger, contract, contract_path)
    assert_recovery_chain(ledger, contract)
    stage = H.next_stage(ledger, contract)
    if stage is None:
        return {'passed': True, 'advanced': False, 'blocked': False, 'complete': True}
    version = contract['githubInfrastructureAudit']['apiVersion']
    kind = (contract['firstRealRun']['stageLaunchHints'].get(stage) or {}).get('kind')
    if kind == 'local-source-transition-preparation':
        pr_token = os.environ.get(str(contract['firstRealRun']['controller'].get('evidencePrTokenEnv', 'MTE_PRODUCTION_EVIDENCE_PR_TOKEN')), '').strip()
        if not pr_token:
            raise ControllerError('MTE_PRODUCTION_EVIDENCE_PR_TOKEN is required only for evidence PR creation; use a local token with Contents:write and Pull requests:write')
        return advance_local_evidence_pr(path, ledger, stage, contract, contract_path, pr_token, version)
    if kind == 'merged-pr-transition':
        return advance_merged_pr(path, ledger, stage, contract, contract_path, token, version)
    if kind == 'local-checkout-reconciliation':
        return advance_checkout_reconciliation(path, ledger, stage, contract, contract_path, token, version)
    if not automated_kind(stage, contract):
        return boundary_result(stage, ledger, contract)
    reused = reuse_previous_run_if_configured(path, ledger, stage, contract, contract_path, token, version)
    if reused is not None:
        return reused

    assert_live_default_branch_head(ledger, token, version)
    pending = ledger.get('pendingLaunch')
    if pending is None:
        ledger['pendingLaunch'] = create_pending(stage, ledger, contract, operator_inputs)
        write_and_validate(path, ledger, contract, contract_path)
        ledger = json.loads(path.read_text(encoding='utf-8'))
        pending = ledger['pendingLaunch']
    else:
        if operator_inputs and operator_inputs != (pending.get('operatorInputs') or {}):
            raise ControllerError('a pending launch already exists; resume it without changing its sealed operator inputs')

    nonce = str(pending['runIntentNonce'])
    expected_dispatches = resolve_dispatches(stage, ledger, contract, dict(pending.get('operatorInputs') or {}), nonce)
    normalized_pending = [{'workflow': x.get('workflow'), 'inputs': x.get('inputs')} for x in pending.get('dispatches') or []]
    normalized_expected = [{'workflow': x.get('workflow'), 'inputs': x.get('inputs')} for x in expected_dispatches]
    if normalized_pending != normalized_expected:
        raise ControllerError('pending launch workflow/input plan no longer matches the sealed production execution contract')
    # Persist the pending intent before each dispatch. On resume, recover by nonce before re-dispatching.
    for item in pending['dispatches']:
        if item.get('runId'):
            continue
        recovered = recover_run_by_nonce(ledger, item['workflow'], nonce, token, version)
        run_id = recovered
        if run_id is None:
            assert_live_default_branch_head(ledger, token, version)
            run_id = dispatch_workflow(ledger, item['workflow'], item['inputs'], token, version)
            if run_id is None:
                # Compatibility fallback for APIs that acknowledge dispatch without a run id.
                for _ in range(12):
                    time.sleep(max(0.05, min(poll_seconds, 5)))
                    run_id = recover_run_by_nonce(ledger, item['workflow'], nonce, token, version)
                    if run_id:
                        break
            if run_id is None:
                raise ControllerError(f'dispatch was accepted but the workflow run could not be recovered for {item["workflow"]}; pending intent remains sealed')
        item['runId'] = str(run_id)
        write_and_validate(path, ledger, contract, contract_path)

    run_ids = [str(x['runId']) for x in pending['dispatches']]
    for run_id in run_ids:
        run = wait_for_run(ledger, run_id, token, version, poll_seconds, timeout_seconds)
        if str(run.get('conclusion') or '') != 'success':
            raise ControllerError(f'workflow run {run_id} completed with conclusion={run.get("conclusion")!r}; pending launch is retained and may be retried explicitly')

    assert_live_default_branch_head(ledger, token, version)
    observations = H.verify_run_stage(stage, run_ids, ledger, contract, token, None, expected_nonce=nonce)
    created_pr = None
    if H.created_pr_config(stage, contract):
        created_pr = H.verify_created_pr_stage(stage, nonce, ledger, contract, token, None)
    recovery_snapshot = capture_recovery(stage, ledger, observations, contract, token, version)
    completed = record_verified_stage(ledger, stage, nonce, observations, contract, pending.get('operatorInputs') or {}, pull_request_created=created_pr, recovery_snapshot=recovery_snapshot)
    ledger.pop('pendingLaunch', None)
    write_and_validate(path, ledger, contract, contract_path)
    return {
        'passed': True,
        'advanced': True,
        'recordedStages': completed,
        'runIntentNonce': nonce,
        'runIds': run_ids,
        'nextStage': H.next_stage(ledger, contract),
        'nextStageLaunch': H.stage_hint(H.next_stage(ledger, contract), contract),
    }


def retry_failed(path: Path, contract: dict[str, Any], contract_path: Path, token: str, poll_seconds: float, timeout_seconds: float) -> dict[str, Any]:
    ledger = json.loads(path.read_text(encoding='utf-8'))
    H.validate(ledger, contract, contract_path)
    assert_recovery_chain(ledger, contract)
    pending = ledger.get('pendingLaunch')
    if not pending:
        raise ControllerError('there is no pending launch to retry')
    version = contract['githubInfrastructureAudit']['apiVersion']
    statuses = []
    for item in pending['dispatches']:
        run_id = item.get('runId') or recover_run_by_nonce(ledger, item['workflow'], pending['runIntentNonce'], token, version)
        if not run_id:
            raise ControllerError('pending launch has an undispatched/unrecoverable workflow; use advance/resume instead of retry-failed')
        item['runId'] = str(run_id)
        run = get_run(ledger, str(run_id), token, version)
        if str(run.get('status')) != 'completed':
            raise ControllerError(f'workflow run {run_id} is not completed; use resume instead of retry-failed')
        statuses.append({'workflow': item['workflow'], 'runId': str(run_id), 'conclusion': str(run.get('conclusion') or '')})
    if all(x['conclusion'] == 'success' for x in statuses):
        raise ControllerError('all pending runs succeeded; use resume to verify and record them')
    ledger.setdefault('failedLaunches', []).append({
        'stage': pending['stage'],
        'runIntentNonce': pending['runIntentNonce'],
        'sourceHeadSha': pending['sourceHeadSha'],
        'recordedAt': H.now_iso(),
        'runs': statuses,
    })
    saved_inputs = dict(pending.get('operatorInputs') or {})
    ledger.pop('pendingLaunch', None)
    write_and_validate(path, ledger, contract, contract_path)
    return advance(path, contract, contract_path, token, saved_inputs, poll_seconds, timeout_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description='Launch/resume verified GitHub workflow stages for the first real V1 run. Human/PR/local evidence boundaries remain explicit.')
    parser.add_argument('--contract', type=Path, default=DEFAULT_CONTRACT)
    sub = parser.add_subparsers(dest='command', required=True)

    p = sub.add_parser('plan')
    p.add_argument('--ledger', type=Path, required=True)

    for name in ['advance', 'resume']:
        p = sub.add_parser(name)
        p.add_argument('--ledger', type=Path, required=True)
        p.add_argument('--input', action='append', default=[])
        p.add_argument('--token-env', default='MTE_PRODUCTION_CONTROLLER_TOKEN')
        p.add_argument('--poll-seconds', type=float)
        p.add_argument('--timeout-seconds', type=float)

    p = sub.add_parser('retry-failed')
    p.add_argument('--ledger', type=Path, required=True)
    p.add_argument('--token-env', default='MTE_PRODUCTION_CONTROLLER_TOKEN')
    p.add_argument('--poll-seconds', type=float)
    p.add_argument('--timeout-seconds', type=float)

    args = parser.parse_args()
    contract_path = args.contract.resolve()
    contract = H.load_contract(contract_path)
    controller_cfg = contract['firstRealRun']['controller']
    ledger = json.loads(args.ledger.read_text(encoding='utf-8'))
    H.validate(ledger, contract, contract_path)
    assert_recovery_chain(ledger, contract)

    if args.command == 'plan':
        stage = H.next_stage(ledger, contract)
        hint = H.stage_hint(stage, contract)
        print(json.dumps({
            'passed': True,
            'controllerRevision': CONTROLLER_REVISION,
            'nextStage': stage,
            'automated': bool(stage and automated_kind(stage, contract)),
            'pendingLaunch': ledger.get('pendingLaunch'),
            'requiredOperatorInputs': (hint or {}).get('controllerRequiredInputs', []) if isinstance(hint, dict) else [],
            'nextStageLaunch': hint,
        }, indent=2))
        return 0

    token = os.environ.get(args.token_env, '').strip()
    if not token:
        raise ControllerError(f'{args.token_env} is required; use a local fine-grained token with Actions:write, Contents:read and Pull requests:read; evidence PR creation uses the separate local MTE_PRODUCTION_EVIDENCE_PR_TOKEN')
    poll = args.poll_seconds if args.poll_seconds is not None else float(controller_cfg['defaultPollSeconds'])
    timeout = args.timeout_seconds if args.timeout_seconds is not None else float(controller_cfg['defaultTimeoutSeconds'])
    if poll <= 0 or timeout <= 0:
        raise ControllerError('poll/timeout values must be positive')

    if args.command == 'retry-failed':
        result = retry_failed(args.ledger, contract, contract_path, token, poll, timeout)
    else:
        inputs = parse_inputs(args.input)
        result = advance(args.ledger, contract, contract_path, token, inputs, poll, timeout)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ControllerError, H.HandoffError) as exc:
        print(json.dumps({'passed': False, 'error': str(exc)}, indent=2))
        raise SystemExit(2)
