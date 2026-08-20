from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = ROOT / 'engine'
import sys
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.run_plan import load_run_plan
from release_evidence import load_json, sha256_file, validate_controlled_manifest, validate_smoke_observation
from v1_evidence_orchestrator import read_session, read_store_handoff, require_release_identity

CHECKPOINT_REVISION = 'rev29-manual-boundary-checkpoint-v1'
HEX64 = re.compile(r'^[0-9a-f]{64}$')


class ManualCheckpointError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def digest_body(value: dict[str, Any]) -> str:
    body = dict(value)
    body.pop('checkpointSha256', None)
    return hashlib.sha256(canonical(body)).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def parse_evidence(items: list[str]) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for raw in items:
        if '=' not in raw:
            raise ManualCheckpointError('--evidence values must use role=/absolute/or/relative/path')
        role, path = raw.split('=', 1)
        role = role.strip()
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,63}', role):
            raise ManualCheckpointError(f'invalid evidence role: {role!r}')
        if role in out:
            raise ManualCheckpointError(f'duplicate evidence role: {role}')
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_file():
            raise ManualCheckpointError(f'evidence file does not exist: {resolved}')
        if resolved.is_symlink():
            raise ManualCheckpointError(f'evidence file must not be a symlink: {resolved}')
        out[role] = resolved
    return out


def evidence_descriptor(role: str, path: Path) -> dict[str, Any]:
    return {'role': role, 'fileName': path.name, 'sha256': sha256_file(path), 'sizeBytes': path.stat().st_size}


def _require_roles(evidence: dict[str, Path], required: set[str]) -> None:
    if set(evidence) != required:
        missing = sorted(required - set(evidence))
        extra = sorted(set(evidence) - required)
        raise ManualCheckpointError(f'manual checkpoint evidence roles mismatch; missing={missing}, extra={extra}')


def _major(value: Any) -> int:
    if not isinstance(value, str) or not re.fullmatch(r'\d+(?:\.\d+){0,3}', value):
        raise ManualCheckpointError(f'invalid Chrome version: {value!r}')
    return int(value.split('.', 1)[0])


def _release_browser_majors() -> tuple[int, int]:
    state = load_json(ROOT / 'release-control' / 'release-state.json', 'release state')
    audit = state.get('audit') if isinstance(state.get('audit'), dict) else {}
    baseline = audit.get('chromeBaselineMajor')
    stable = audit.get('currentStableMajorAtAudit')
    if isinstance(baseline, bool) or not isinstance(baseline, int) or baseline < 1:
        raise ManualCheckpointError('release-state Chrome baseline major is invalid')
    if isinstance(stable, bool) or not isinstance(stable, int) or stable < baseline:
        raise ManualCheckpointError('release-state current Stable Chrome major is invalid')
    return baseline, stable


def validate_benchmark_review(evidence: dict[str, Path]) -> dict[str, Any]:
    _require_roles(evidence, {'run-plan', 'benchmark-review'})
    run_plan = load_run_plan(evidence['run-plan'], require_ready=True)
    review = load_json(evidence['benchmark-review'], 'sealed benchmark review')
    if review.get('schemaVersion') != 1 or review.get('reviewRevision') != 'rev10-production-benchmark-review-v1':
        raise ManualCheckpointError('unsupported benchmark review schema/revision')
    expected = review.get('reviewRecordSha256')
    if not isinstance(expected, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', expected):
        raise ManualCheckpointError('benchmark review is not sealed with a valid reviewRecordSha256')
    body = dict(review)
    body.pop('reviewRecordSha256', None)
    actual = 'sha256:' + hashlib.sha256(canonical(body)).hexdigest()
    if actual != expected:
        raise ManualCheckpointError('benchmark review content digest mismatch')
    if review.get('runPlanSha256') != run_plan.get('runPlanSha256'):
        raise ManualCheckpointError('benchmark review is not bound to the exact ready run plan')
    report_id = review.get('reportId')
    if not isinstance(report_id, str) or not report_id.strip():
        raise ManualCheckpointError('benchmark review reportId is missing')
    return {
        'kind': 'benchmark-review',
        'runPlanSha256': run_plan['runPlanSha256'],
        'reviewRecordSha256': review['reviewRecordSha256'],
        'reportId': report_id,
    }


def validate_exact_browser_smoke(evidence: dict[str, Path], *, source_head_sha: str, release_class: str) -> dict[str, Any]:
    _require_roles(evidence, {'controlled-manifest', 'orchestration-session', 'browser-observation-a', 'browser-observation-b'})
    manifest, manifest_sha = validate_controlled_manifest(evidence['controlled-manifest'], require_v1=True)
    if manifest.get('releaseClass') != release_class:
        raise ManualCheckpointError('controlled manifest releaseClass differs from the operational ledger')
    if manifest.get('sourceHeadSha') != source_head_sha:
        raise ManualCheckpointError('controlled manifest sourceHeadSha differs from the operational ledger cursor')
    session = read_session(evidence['orchestration-session'], 'native-smoke-complete')
    require_release_identity(session, manifest, manifest_sha)
    observations: list[dict[str, Any]] = []
    for role in ('browser-observation-a', 'browser-observation-b'):
        obs = load_json(evidence[role], role)
        validate_smoke_observation(obs, manifest=manifest, manifest_sha256=manifest_sha, require_engine_profile=False)
        if obs.get('kind') != 'unpacked-extension':
            raise ManualCheckpointError('exact browser checkpoint accepts only unpacked-extension observations')
        if obs.get('orchestrationSessionSha256') != session.get('sessionSha256'):
            raise ManualCheckpointError('browser observation is not bound to the native-smoke orchestration session')
        observations.append(obs)
    majors = sorted(_major(x.get('browserVersion')) for x in observations)
    baseline, stable = _release_browser_majors()
    if majors != sorted([baseline, stable]):
        raise ManualCheckpointError(f'browser smoke must contain exactly Chrome {baseline} and Chrome {stable}; observed={majors}')
    return {
        'kind': 'exact-browser-smoke',
        'controlledManifestSha256': manifest_sha,
        'orchestrationSessionSha256': session['sessionSha256'],
        'browserMajors': majors,
        'observationSha256ByMajor': {str(_major(obs['browserVersion'])): sha256_file(evidence[role]) for role, obs in zip(('browser-observation-a', 'browser-observation-b'), observations)},
    }


def validate_store_installed_smoke(evidence: dict[str, Path], *, source_head_sha: str, release_class: str) -> dict[str, Any]:
    required = {'controlled-manifest', 'orchestration-session', 'store-submission-handoff', 'store-candidate-metadata', 'store-candidate-zip', 'store-observation-a', 'store-observation-b'}
    _require_roles(evidence, required)
    if release_class != 'public-v1':
        raise ManualCheckpointError('Store-installed manual checkpoint is valid only for public-v1')
    manifest, manifest_sha = validate_controlled_manifest(evidence['controlled-manifest'], require_v1=True)
    if manifest.get('releaseClass') != 'public-v1' or manifest.get('sourceHeadSha') != source_head_sha:
        raise ManualCheckpointError('public controlled manifest identity differs from the operational ledger')
    session = read_session(evidence['orchestration-session'], 'evidence-promoted')
    require_release_identity(session, manifest, manifest_sha)
    handoff = read_store_handoff(evidence['store-submission-handoff'])
    if handoff.get('controlledManifestSha256') != manifest_sha or handoff.get('orchestrationSessionSha256') != session.get('sessionSha256'):
        raise ManualCheckpointError('Store submission handoff is not bound to this controlled manifest/orchestration session')
    candidate = load_json(evidence['store-candidate-metadata'], 'Store candidate metadata')
    if candidate.get('schemaVersion') != 2 or candidate.get('controlledManifestSha256') != manifest_sha:
        raise ManualCheckpointError('Store candidate metadata is not bound to this controlled manifest')
    if candidate.get('storeSubmissionHandoffSha256') != handoff.get('handoffSha256'):
        raise ManualCheckpointError('Store candidate metadata is not bound to this Store submission handoff')
    extension = manifest.get('extension') if isinstance(manifest.get('extension'), dict) else {}
    if candidate.get('sha256') != extension.get('sha256'):
        raise ManualCheckpointError('Store candidate sha256 differs from the controlled Extension')
    candidate_zip = evidence['store-candidate-zip']
    if candidate.get('artifact') != candidate_zip.name or sha256_file(candidate_zip) != candidate.get('sha256'):
        raise ManualCheckpointError('Store candidate ZIP bytes/name differ from the approved Store candidate metadata')
    observations: list[dict[str, Any]] = []
    roles = ('store-observation-a', 'store-observation-b')
    for role in roles:
        obs = load_json(evidence[role], role)
        validate_smoke_observation(obs, manifest=manifest, manifest_sha256=manifest_sha, require_engine_profile=False)
        if obs.get('kind') != 'store-installed-extension':
            raise ManualCheckpointError('Store manual checkpoint accepts only store-installed-extension observations')
        if obs.get('orchestrationSessionSha256') != session.get('sessionSha256'):
            raise ManualCheckpointError('Store observation orchestration hash differs from the evidence-promoted session')
        if obs.get('storeSubmissionHandoffSha256') != handoff.get('handoffSha256') or obs.get('storeCandidateSha256') != candidate.get('sha256'):
            raise ManualCheckpointError('Store observation is not bound to the exact Store candidate/handoff')
        observations.append(obs)
    majors = sorted(_major(x.get('browserVersion')) for x in observations)
    baseline, stable = _release_browser_majors()
    if majors != sorted([baseline, stable]):
        raise ManualCheckpointError(f'Store smoke must contain exactly Chrome {baseline} and Chrome {stable}; observed={majors}')
    return {
        'kind': 'store-installed-browser-smoke',
        'controlledManifestSha256': manifest_sha,
        'orchestrationSessionSha256': session['sessionSha256'],
        'storeSubmissionHandoffSha256': handoff['handoffSha256'],
        'storeCandidateSha256': candidate['sha256'],
        'storeItemIds': sorted(set(str(x.get('storeItemId')) for x in observations)),
        'browserMajors': majors,
        'observationSha256ByMajor': {str(_major(obs['browserVersion'])): sha256_file(evidence[role]) for role, obs in zip(roles, observations)},
    }


def validate_semantics(stage: str, evidence: dict[str, Path], *, source_head_sha: str, release_class: str) -> dict[str, Any]:
    if stage == 'benchmark-review':
        return validate_benchmark_review(evidence)
    if stage == 'chrome-148-and-stable-smoke':
        return validate_exact_browser_smoke(evidence, source_head_sha=source_head_sha, release_class=release_class)
    if stage == 'store-installed-chrome-smoke':
        return validate_store_installed_smoke(evidence, source_head_sha=source_head_sha, release_class=release_class)
    raise ManualCheckpointError(f'unsupported manual checkpoint stage: {stage}')


def api_get(url: str, token: str, api_version: str) -> Any:
    req = urllib.request.Request(url, headers={
        'Accept': 'application/vnd.github+json',
        'Authorization': f'Bearer {token}',
        'X-GitHub-Api-Version': api_version,
        'User-Agent': 'mte-manual-boundary-checkpoint',
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')[:500]
        raise ManualCheckpointError(f'GitHub API request failed with HTTP {exc.code}: {body}') from exc
    except urllib.error.URLError as exc:
        raise ManualCheckpointError(f'GitHub API request failed: {exc.reason}') from exc


def operator_and_head(repository: str, default_branch: str, token: str | None, snapshot: Path | None, api_version: str, expected_repository_id: int | str | None = None) -> tuple[dict[str, str], str]:
    if snapshot is not None:
        value = json.loads(snapshot.read_text(encoding='utf-8'))
        actor = value.get('actor') if isinstance(value.get('actor'), dict) else {}
        head = str(value.get('defaultBranchHeadSha', '')).lower()
        repository_id = value.get('repositoryId')
        live_default_branch = str(value.get('defaultBranch', default_branch))
    else:
        if not token:
            raise ManualCheckpointError('live manual checkpoint requires a local GitHub token or --actor-snapshot for tests')
        actor = api_get('https://api.github.com/user', token, api_version)
        owner, repo = repository.split('/', 1)
        base = f'https://api.github.com/repos/{urllib.parse.quote(owner, safe="")}/{urllib.parse.quote(repo, safe="")}'
        repo_meta = api_get(base, token, api_version)
        repository_id = repo_meta.get('id')
        live_default_branch = str(repo_meta.get('default_branch', ''))
        ref = urllib.parse.quote(default_branch, safe='')
        commit = api_get(f'{base}/commits/{ref}', token, api_version)
        head = str(commit.get('sha', '')).lower()
    actor_id = str(actor.get('id', ''))
    login = str(actor.get('login', ''))
    if not actor_id.isdigit() or not login:
        raise ManualCheckpointError('GitHub operator identity is invalid')
    if expected_repository_id is not None and str(repository_id) != str(expected_repository_id):
        raise ManualCheckpointError('live GitHub repository id differs from the sealed onboarding/ledger repository identity')
    if live_default_branch != default_branch:
        raise ManualCheckpointError('live GitHub default branch differs from the sealed onboarding/ledger default branch')
    if not re.fullmatch(r'[0-9a-f]{40}', head):
        raise ManualCheckpointError('default branch head from GitHub is invalid')
    return {'id': actor_id, 'login': login}, head


def create_checkpoint(*, stage: str, ledger: dict[str, Any], evidence: dict[str, Path], actor: dict[str, str], semantic: dict[str, Any]) -> dict[str, Any]:
    value = {
        'schemaVersion': 1,
        'revision': CHECKPOINT_REVISION,
        'stage': stage,
        'releaseId': ledger['releaseId'],
        'releaseClass': ledger['releaseClass'],
        'repository': ledger['repository'],
        'repositoryId': ledger['repositoryId'],
        'sourceHeadSha': ledger['currentSourceHeadSha'],
        'operator': actor,
        'reviewedAtUtc': now_iso(),
        'evidence': [evidence_descriptor(role, evidence[role]) for role in sorted(evidence)],
        'semanticBinding': semantic,
        'notice': 'Operational manual-boundary checkpoint only. It binds reviewed evidence bytes and operator identity; it is not a substitute for release evidence.',
    }
    value['checkpointSha256'] = digest_body(value)
    return value


def validate_checkpoint(value: dict[str, Any], *, stage: str, ledger: dict[str, Any]) -> None:
    if value.get('schemaVersion') != 1 or value.get('revision') != CHECKPOINT_REVISION:
        raise ManualCheckpointError('unsupported manual checkpoint schema/revision')
    if value.get('stage') != stage or value.get('releaseId') != ledger.get('releaseId') or value.get('releaseClass') != ledger.get('releaseClass'):
        raise ManualCheckpointError('manual checkpoint release/stage identity mismatch')
    if value.get('repository') != ledger.get('repository') or value.get('repositoryId') != ledger.get('repositoryId'):
        raise ManualCheckpointError('manual checkpoint repository identity mismatch')
    if value.get('sourceHeadSha') != ledger.get('currentSourceHeadSha'):
        raise ManualCheckpointError('manual checkpoint sourceHeadSha differs from the ledger cursor')
    actor = value.get('operator') if isinstance(value.get('operator'), dict) else {}
    if str(actor.get('id')) not in {str(x) for x in ledger.get('authorizedOperatorIds', [])}:
        raise ManualCheckpointError('manual checkpoint operator is not in the sealed production operator allowlist')
    if value.get('checkpointSha256') != digest_body(value):
        raise ManualCheckpointError('manual checkpointSha256 mismatch')
    evidence = value.get('evidence')
    if not isinstance(evidence, list) or not evidence:
        raise ManualCheckpointError('manual checkpoint evidence list is empty')
    for item in evidence:
        if not isinstance(item, dict) or not isinstance(item.get('role'), str) or not HEX64.fullmatch(str(item.get('sha256', ''))):
            raise ManualCheckpointError('manual checkpoint evidence descriptor is invalid')


def validate_checkpoint_evidence(value: dict[str, Any], evidence: dict[str, Path], *, ledger: dict[str, Any]) -> dict[str, Any]:
    stage = str(value.get('stage', ''))
    semantic = validate_semantics(stage, evidence, source_head_sha=ledger['currentSourceHeadSha'], release_class=ledger['releaseClass'])
    if semantic != value.get('semanticBinding'):
        raise ManualCheckpointError('manual checkpoint semantic binding differs from the supplied evidence bytes')
    expected = {item['role']: item for item in value.get('evidence', []) if isinstance(item, dict) and isinstance(item.get('role'), str)}
    if set(expected) != set(evidence):
        raise ManualCheckpointError('manual checkpoint evidence role set differs from the supplied evidence files')
    for role, path in evidence.items():
        actual = evidence_descriptor(role, path)
        if expected.get(role) != actual:
            raise ManualCheckpointError(f'manual checkpoint evidence descriptor mismatch for {role}')
    return semantic


def main() -> int:
    parser = argparse.ArgumentParser(description='Create/verify content-addressed, GitHub-identity-bound checkpoints for human production boundaries.')
    parser.add_argument('--stage', choices=['benchmark-review', 'chrome-148-and-stable-smoke', 'store-installed-chrome-smoke'], required=True)
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--contract', type=Path, default=ROOT / 'release-control' / 'production-execution-contract.json')
    parser.add_argument('--evidence', action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--token-env', default='MTE_PRODUCTION_CONTROLLER_TOKEN')
    parser.add_argument('--actor-snapshot', type=Path, help='Tests/offline validation only: JSON with actor{id,login} and defaultBranchHeadSha.')
    args = parser.parse_args()

    handoff_spec = importlib.util.spec_from_file_location('mte_handoff_for_manual_checkpoint', ROOT / 'scripts' / 'first_real_run_handoff.py')
    if handoff_spec is None or handoff_spec.loader is None:
        raise ManualCheckpointError('cannot load first-real-run handoff validator')
    handoff = importlib.util.module_from_spec(handoff_spec)
    handoff_spec.loader.exec_module(handoff)
    contract_path = args.contract.resolve()
    contract = handoff.load_contract(contract_path)
    ledger = json.loads(args.ledger.read_text(encoding='utf-8'))
    handoff.validate(ledger, contract, contract_path)
    if handoff.next_stage(ledger, contract) != args.stage:
        raise ManualCheckpointError(f'ledger next stage is {handoff.next_stage(ledger, contract)!r}, not {args.stage!r}')

    evidence = parse_evidence(args.evidence)
    semantic = validate_semantics(args.stage, evidence, source_head_sha=ledger['currentSourceHeadSha'], release_class=ledger['releaseClass'])
    token = None if args.actor_snapshot else os.environ.get(args.token_env, '').strip()
    actor, live_head = operator_and_head(ledger['repository'], ledger['defaultBranch'], token, args.actor_snapshot, contract['githubInfrastructureAudit']['apiVersion'], ledger['repositoryId'])
    if actor['id'] not in {str(x) for x in ledger['authorizedOperatorIds']}:
        raise ManualCheckpointError('current GitHub operator id is not in the sealed production operator allowlist')
    if live_head != ledger['currentSourceHeadSha']:
        raise ManualCheckpointError('default branch moved since the ledger cursor; do not approve a stale manual boundary')
    checkpoint = create_checkpoint(stage=args.stage, ledger=ledger, evidence=evidence, actor=actor, semantic=semantic)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(args.output.suffix + '.tmp')
    temp.write_text(json.dumps(checkpoint, indent=2) + '\n', encoding='utf-8')
    temp.replace(args.output)
    print(json.dumps({'passed': True, 'stage': args.stage, 'checkpoint': str(args.output), 'checkpointSha256': checkpoint['checkpointSha256'], 'operator': actor, 'semanticBinding': semantic}, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ManualCheckpointError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({'passed': False, 'error': str(exc)}, indent=2))
        raise SystemExit(2)
