from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / 'release-control' / 'production-execution-contract.json'
RECOVERY_REVISION = 'rev33-first-real-run-recovery-v2'
BUNDLE_REVISION = 'rev33-first-real-run-recovery-bundle-v2'
RESTORE_REVISION = 'rev33-recovery-restore-v1'
HEX64 = re.compile(r'^[0-9a-f]{64}$')


class RecoveryError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def safe_name(value: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9._-]+', '_', value).strip('._')
    if not cleaned:
        raise RecoveryError('artifact/stage name cannot be normalized safely')
    return cleaned[:120]


def recovery_root_for(ledger: dict[str, Any], root: Path | None = None) -> Path:
    base = (root or (ROOT / 'release' / 'recovery')).resolve()
    return base / safe_name(str(ledger['releaseId']))


def repo_base(ledger: dict[str, Any]) -> str:
    owner, repo = str(ledger['repository']).split('/', 1)
    return f'https://api.github.com/repos/{urllib.parse.quote(owner, safe="")}/{urllib.parse.quote(repo, safe="")}'


def _headers(token: str, version: str) -> dict[str, str]:
    return {
        'Accept': 'application/vnd.github+json',
        'Authorization': f'Bearer {token}',
        'X-GitHub-Api-Version': version,
        'User-Agent': 'mte-first-real-run-recovery',
    }


def api_get_json(url: str, token: str, version: str) -> Any:
    req = urllib.request.Request(url, headers=_headers(token, version))
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')[:800]
        raise RecoveryError(f'GitHub API GET {url} failed with HTTP {exc.code}: {body}') from exc
    except urllib.error.URLError as exc:
        raise RecoveryError(f'GitHub API GET {url} failed: {exc.reason}') from exc


def api_get_paginated(url: str, token: str, version: str) -> list[dict[str, Any]]:
    page = 1
    out: list[dict[str, Any]] = []
    while True:
        sep = '&' if '?' in url else '?'
        payload = api_get_json(f'{url}{sep}per_page=100&page={page}', token, version)
        items = payload.get('artifacts') if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise RecoveryError('GitHub paginated response has invalid shape')
        out.extend(x for x in items if isinstance(x, dict))
        if len(items) < 100:
            return out
        page += 1


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


def download_artifact_archive(ledger: dict[str, Any], artifact_id: int, token: str, version: str) -> bytes:
    # First request is authenticated to GitHub. The redirect target is a short-lived
    # signed URL and MUST be fetched without the GitHub Authorization header.
    url = f'{repo_base(ledger)}/actions/artifacts/{artifact_id}/zip'
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, headers=_headers(token, version))
    try:
        opener.open(req, timeout=45)
        raise RecoveryError('artifact download unexpectedly returned without a redirect')
    except urllib.error.HTTPError as exc:
        if exc.code == 410:
            raise RecoveryError(f'GitHub artifact {artifact_id} is expired (410 Gone)') from exc
        if exc.code not in {301, 302, 303, 307, 308}:
            body = exc.read().decode('utf-8', errors='replace')[:500]
            raise RecoveryError(f'GitHub artifact {artifact_id} download failed with HTTP {exc.code}: {body}') from exc
        location = exc.headers.get('Location')
        if not location:
            raise RecoveryError(f'GitHub artifact {artifact_id} redirect has no Location header')
    try:
        with urllib.request.urlopen(urllib.request.Request(location, headers={'User-Agent': 'mte-first-real-run-recovery'}), timeout=120) as response:
            return response.read()
    except urllib.error.URLError as exc:
        raise RecoveryError(f'artifact {artifact_id} signed download failed: {exc.reason}') from exc


def _safe_run(run: dict[str, Any]) -> dict[str, Any]:
    actor = run.get('actor') if isinstance(run.get('actor'), dict) else {}
    return {
        'id': int(run.get('id', 0)),
        'name': str(run.get('name', '')),
        'path': str(run.get('path', '')),
        'display_title': str(run.get('display_title', '')),
        'event': str(run.get('event', '')),
        'status': str(run.get('status', '')),
        'conclusion': str(run.get('conclusion', '')),
        'head_branch': str(run.get('head_branch', '')),
        'head_sha': str(run.get('head_sha', '')).lower(),
        'run_number': run.get('run_number'),
        'run_attempt': run.get('run_attempt'),
        'created_at': run.get('created_at'),
        'updated_at': run.get('updated_at'),
        'html_url': str(run.get('html_url', '')),
        'actor': {'id': str(actor.get('id', '')), 'login': str(actor.get('login', ''))},
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8')


def _manifest_hash(value: dict[str, Any]) -> str:
    body = dict(value)
    body.pop('manifestSha256', None)
    return sha256_bytes(canonical(body))


def verify_snapshot_dir(stage_dir: Path) -> dict[str, Any]:
    manifest_path = stage_dir / 'recovery-manifest.json'
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise RecoveryError(f'recovery manifest missing: {manifest_path}')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('schemaVersion') != 1 or manifest.get('revision') != RECOVERY_REVISION:
        raise RecoveryError('unsupported recovery snapshot schema/revision')
    if manifest.get('manifestSha256') != _manifest_hash(manifest):
        raise RecoveryError('recovery manifest content digest mismatch')
    listed = manifest.get('files')
    if not isinstance(listed, list):
        raise RecoveryError('recovery manifest file list is invalid')
    expected_paths = set()
    for item in listed:
        rel = str(item.get('path', ''))
        if not rel or rel.startswith('/') or '..' in Path(rel).parts:
            raise RecoveryError('recovery manifest contains an unsafe relative path')
        path = stage_dir / rel
        if not path.is_file() or path.is_symlink():
            raise RecoveryError(f'recovery file missing or symlinked: {rel}')
        if path.stat().st_size != int(item.get('sizeBytes', -1)):
            raise RecoveryError(f'recovery file size mismatch: {rel}')
        if sha256_file(path) != str(item.get('sha256', '')):
            raise RecoveryError(f'recovery file SHA-256 mismatch: {rel}')
        expected_paths.add(rel)
    actual = set()
    for p in stage_dir.rglob('*'):
        if p.is_file() and p.name != 'recovery-manifest.json':
            actual.add(p.relative_to(stage_dir).as_posix())
        if p.is_symlink():
            raise RecoveryError('recovery snapshot contains a symlink')
    if actual != expected_paths:
        raise RecoveryError(f'recovery snapshot contains unlisted/missing files; extra={sorted(actual-expected_paths)}, missing={sorted(expected_paths-actual)}')
    return manifest


def _finalize_snapshot(temp_dir: Path, final_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    files = []
    for path in sorted(p for p in temp_dir.rglob('*') if p.is_file() and p.name != 'recovery-manifest.json'):
        rel = path.relative_to(temp_dir).as_posix()
        files.append({'path': rel, 'sizeBytes': path.stat().st_size, 'sha256': sha256_file(path)})
    manifest['files'] = files
    manifest['manifestSha256'] = _manifest_hash(manifest)
    _write_json(temp_dir / 'recovery-manifest.json', manifest)
    verify_snapshot_dir(temp_dir)
    if final_dir.exists():
        existing = verify_snapshot_dir(final_dir)
        if existing.get('manifestSha256') != manifest['manifestSha256']:
            raise RecoveryError(f'existing recovery snapshot differs from the new snapshot: {final_dir}')
        shutil.rmtree(temp_dir)
    else:
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temp_dir, final_dir)
    return {
        'revision': RECOVERY_REVISION,
        'stage': manifest['stage'],
        'relativePath': final_dir.relative_to(ROOT).as_posix() if final_dir.is_relative_to(ROOT) else str(final_dir),
        'manifestSha256': manifest['manifestSha256'],
        'runIds': list(manifest.get('runIds') or []),
        'artifactCount': int(manifest.get('artifactCount', 0)),
        'capturedAt': manifest['capturedAt'],
    }


def capture_automated_stage(*, ledger: dict[str, Any], stage: str, observations: list[dict[str, Any]], token: str, version: str, root: Path | None = None, minimum_artifacts: int = 0) -> dict[str, Any]:
    run_ids = [str(x.get('runId', '')) for x in observations]
    if not run_ids or any(not x.isdigit() for x in run_ids):
        raise RecoveryError('automated recovery snapshot requires valid run observations')
    final_dir = recovery_root_for(ledger, root) / 'stages' / safe_name(stage)
    if final_dir.exists():
        manifest = verify_snapshot_dir(final_dir)
        if manifest.get('testOnly') is True:
            raise RecoveryError('existing recovery snapshot is test-only and cannot satisfy production capture')
        if manifest.get('runIds') != run_ids or manifest.get('sourceHeadSha') != ledger.get('currentSourceHeadSha'):
            raise RecoveryError('existing recovery snapshot is bound to different run/source identity')
        if int(manifest.get('artifactCount', 0)) < int(minimum_artifacts):
            raise RecoveryError(f'existing recovery snapshot has fewer than the required {minimum_artifacts} artifact(s)')
        return {
            'revision': RECOVERY_REVISION, 'stage': stage,
            'relativePath': final_dir.relative_to(ROOT).as_posix() if final_dir.is_relative_to(ROOT) else str(final_dir),
            'manifestSha256': manifest['manifestSha256'], 'runIds': run_ids,
            'artifactCount': int(manifest.get('artifactCount', 0)), 'capturedAt': manifest['capturedAt'],
        }
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f'.{safe_name(stage)}.', dir=final_dir.parent))
    artifact_count = 0
    run_summaries = []
    try:
        base = repo_base(ledger)
        for observation in observations:
            run_id = str(observation['runId'])
            run = api_get_json(f'{base}/actions/runs/{run_id}', token, version)
            safe_run = _safe_run(run)
            if str(safe_run['id']) != run_id:
                raise RecoveryError(f'run {run_id} identity mismatch while archiving')
            if safe_run['head_sha'] != str(ledger['currentSourceHeadSha']).lower():
                raise RecoveryError(f'run {run_id} head_sha differs from ledger source cursor')
            if safe_run['event'] != 'workflow_dispatch' or safe_run['conclusion'] != 'success':
                raise RecoveryError(f'run {run_id} is not a successful workflow_dispatch run')
            expected_workflow = str(observation.get('workflow', ''))
            if expected_workflow and Path(expected_workflow).name not in safe_run['path'] and expected_workflow not in safe_run['path']:
                raise RecoveryError(f'run {run_id} workflow path differs from the verified run observation')
            if str(safe_run['actor'].get('id', '')) not in {str(x) for x in ledger.get('authorizedOperatorIds', [])}:
                raise RecoveryError(f'run {run_id} actor id is outside the sealed production operator allowlist')
            expected_title = str(observation.get('displayTitle', ''))
            if expected_title and safe_run['display_title'] != expected_title:
                raise RecoveryError(f'run {run_id} display title differs from the verified run observation')
            run_dir = temp_dir / 'runs' / run_id
            _write_json(run_dir / 'run.json', safe_run)
            artifacts = api_get_paginated(f'{base}/actions/runs/{run_id}/artifacts', token, version)
            artifact_meta = []
            for art in sorted(artifacts, key=lambda x: int(x.get('id', 0))):
                aid = int(art.get('id', 0))
                name = str(art.get('name', ''))
                if aid <= 0 or not name:
                    raise RecoveryError(f'run {run_id} returned invalid artifact metadata')
                if art.get('expired') is True:
                    raise RecoveryError(f'run {run_id} artifact {name!r} already expired before recovery capture')
                raw = download_artifact_archive(ledger, aid, token, version)
                local_sha = sha256_bytes(raw)
                api_digest = str(art.get('digest') or '')
                if api_digest:
                    if not re.fullmatch(r'sha256:[0-9a-f]{64}', api_digest):
                        raise RecoveryError(f'artifact {aid} has unsupported digest format')
                    if api_digest != 'sha256:' + local_sha:
                        raise RecoveryError(f'artifact {aid} download digest differs from GitHub artifact digest')
                archive_rel = f'runs/{run_id}/artifacts/{aid}-{safe_name(name)}.zip'
                archive_path = temp_dir / archive_rel
                archive_path.parent.mkdir(parents=True, exist_ok=True)
                archive_path.write_bytes(raw)
                # Prove that the preserved artifact is at least a structurally valid ZIP.
                if not zipfile.is_zipfile(archive_path):
                    raise RecoveryError(f'artifact {aid} is not a valid ZIP archive')
                item = {
                    'id': aid, 'name': name, 'sizeInBytes': int(art.get('size_in_bytes', 0)),
                    'archiveSizeBytes': len(raw), 'archiveSha256': local_sha,
                    'githubDigest': api_digest or None, 'createdAt': art.get('created_at'),
                    'expiresAt': art.get('expires_at'), 'archivePath': archive_rel,
                }
                artifact_meta.append(item)
                artifact_count += 1
            _write_json(run_dir / 'artifacts.json', {'runId': run_id, 'artifacts': artifact_meta})
            run_summaries.append({'runId': run_id, 'workflow': observation.get('workflow'), 'artifactCount': len(artifact_meta)})
        if artifact_count < int(minimum_artifacts):
            raise RecoveryError(f'{stage} recovery expected at least {minimum_artifacts} artifact(s), observed {artifact_count}')
        manifest = {
            'schemaVersion': 1, 'revision': RECOVERY_REVISION, 'kind': 'automated-stage',
            'releaseId': ledger['releaseId'], 'releaseClass': ledger['releaseClass'],
            'repository': ledger['repository'], 'repositoryId': str(ledger['repositoryId']),
            'stage': stage, 'sourceHeadSha': ledger['currentSourceHeadSha'], 'runIds': run_ids,
            'runSummaries': run_summaries, 'artifactCount': artifact_count, 'capturedAt': now_iso(),
            'notice': 'Operational disaster-recovery snapshot. It preserves GitHub workflow run metadata and uploaded artifact ZIP bytes; it is not new release evidence.',
        }
        return _finalize_snapshot(temp_dir, final_dir, manifest)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def capture_offline_test_stage(*, ledger: dict[str, Any], stage: str, observations: list[dict[str, Any]], snapshot_dir: Path, root: Path | None = None) -> dict[str, Any]:
    # Explicitly test-only: preserves synthetic run snapshots for regression tests but
    # verify_ledger_recovery refuses such snapshots for production continuation.
    final_dir = recovery_root_for(ledger, root) / 'stages' / safe_name(stage)
    if final_dir.exists():
        shutil.rmtree(final_dir)
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f'.{safe_name(stage)}.', dir=final_dir.parent))
    try:
        run_ids = [str(x.get('runId', '')) for x in observations]
        for run_id in run_ids:
            candidates = [snapshot_dir / f'{run_id}.json', snapshot_dir / f'run-{run_id}.json']
            src = next((x for x in candidates if x.is_file()), None)
            if src is not None:
                target = temp_dir / 'runs' / run_id / 'run-snapshot.json'
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, target)
        manifest = {
            'schemaVersion': 1, 'revision': RECOVERY_REVISION, 'kind': 'offline-test-stage', 'testOnly': True,
            'releaseId': ledger['releaseId'], 'releaseClass': ledger['releaseClass'], 'repository': ledger['repository'],
            'repositoryId': str(ledger['repositoryId']), 'stage': stage, 'sourceHeadSha': ledger['currentSourceHeadSha'],
            'runIds': run_ids, 'artifactCount': 0, 'capturedAt': now_iso(),
        }
        return _finalize_snapshot(temp_dir, final_dir, manifest)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def capture_manual_stage(*, ledger: dict[str, Any], stage: str, checkpoint_path: Path, evidence: dict[str, Path], root: Path | None = None) -> dict[str, Any]:
    final_dir = recovery_root_for(ledger, root) / 'stages' / safe_name(stage)
    if final_dir.exists():
        manifest = verify_snapshot_dir(final_dir)
        return {
            'revision': RECOVERY_REVISION, 'stage': stage,
            'relativePath': final_dir.relative_to(ROOT).as_posix() if final_dir.is_relative_to(ROOT) else str(final_dir),
            'manifestSha256': manifest['manifestSha256'], 'runIds': [],
            'artifactCount': 0, 'capturedAt': manifest['capturedAt'],
        }
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f'.{safe_name(stage)}.', dir=final_dir.parent))
    try:
        cp = checkpoint_path.resolve()
        if not cp.is_file() or cp.is_symlink():
            raise RecoveryError('manual checkpoint file is missing or symlinked')
        dst = temp_dir / 'manual' / 'checkpoint.json'
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cp, dst)
        roles = []
        for role, path in sorted(evidence.items()):
            if not path.is_file() or path.is_symlink():
                raise RecoveryError(f'manual evidence {role} is missing or symlinked')
            rel = f'manual/evidence/{safe_name(role)}--{safe_name(path.name)}'
            target = temp_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            roles.append({'role': role, 'sourceFileName': path.name, 'archivePath': rel, 'sha256': sha256_file(target), 'sizeBytes': target.stat().st_size})
        manifest = {
            'schemaVersion': 1, 'revision': RECOVERY_REVISION, 'kind': 'manual-stage',
            'releaseId': ledger['releaseId'], 'releaseClass': ledger['releaseClass'],
            'repository': ledger['repository'], 'repositoryId': str(ledger['repositoryId']),
            'stage': stage, 'sourceHeadSha': ledger['currentSourceHeadSha'], 'runIds': [],
            'artifactCount': 0, 'manualEvidence': roles, 'capturedAt': now_iso(),
            'notice': 'Operational disaster-recovery snapshot of already-reviewed manual checkpoint inputs; it does not replace semantic review.',
        }
        return _finalize_snapshot(temp_dir, final_dir, manifest)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def snapshot_path_from_summary(summary: dict[str, Any]) -> Path:
    raw = str(summary.get('relativePath', ''))
    if not raw:
        raise RecoveryError('recovery summary relativePath is missing')
    path = Path(raw)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def verify_summary(summary: dict[str, Any], *, stage: str, expected_run_ids: list[str] | None = None, source_head_sha: str | None = None) -> dict[str, Any]:
    if summary.get('revision') != RECOVERY_REVISION or summary.get('stage') != stage:
        raise RecoveryError(f'{stage} recovery summary revision/stage mismatch')
    path = snapshot_path_from_summary(summary)
    manifest = verify_snapshot_dir(path)
    if manifest.get('manifestSha256') != summary.get('manifestSha256'):
        raise RecoveryError(f'{stage} recovery summary manifest hash mismatch')
    if expected_run_ids is not None and list(manifest.get('runIds') or []) != [str(x) for x in expected_run_ids]:
        raise RecoveryError(f'{stage} recovery run-id binding mismatch')
    if source_head_sha is not None and manifest.get('sourceHeadSha') != source_head_sha:
        raise RecoveryError(f'{stage} recovery source commit binding mismatch')
    return manifest


def verify_ledger_recovery(ledger: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    verified: dict[str, dict[str, Any]] = {}
    automated = {'workflow', 'workflow-set'}
    manual = set(contract['firstRealRun'].get('manualReviewBoundaries') or [])
    for record in ledger.get('records') or []:
        stage = str(record.get('stage', ''))
        kind = ((contract['firstRealRun'].get('stageLaunchHints') or {}).get(stage) or {}).get('kind')
        if kind in automated or stage in manual:
            summary = record.get('recoverySnapshot')
            ref = record.get('recoverySnapshotRef')
            if isinstance(summary, dict):
                runs = [str(x.get('runId')) for x in record.get('runObservations') or []] if kind in automated else []
                manifest = verify_summary(summary, stage=stage, expected_run_ids=runs, source_head_sha=str(record.get('sourceHeadShaBefore', '')))
                if manifest.get('testOnly') is True:
                    raise RecoveryError(f'{stage} recovery snapshot is test-only and cannot authorize production continuation')
                verified[stage] = {'manifestSha256': manifest['manifestSha256'], 'relativePath': summary['relativePath']}
            elif isinstance(ref, dict):
                source_stage = str(ref.get('stage', ''))
                source = verified.get(source_stage)
                if not source or source.get('manifestSha256') != ref.get('manifestSha256'):
                    raise RecoveryError(f'{stage} recovery reference does not resolve to a previously verified snapshot')
                verified[stage] = source
            else:
                raise RecoveryError(f'{stage} is missing its required disaster-recovery snapshot/reference')
    return {'passed': True, 'verifiedStages': sorted(verified)}


def _load_handoff_module():
    tool = ROOT / 'scripts' / 'first_real_run_handoff.py'
    spec = importlib.util.spec_from_file_location('mte_first_real_run_handoff_recovery', tool)
    if spec is None or spec.loader is None:
        raise RecoveryError('could not load first-real-run handoff module')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_source_integrity_module():
    tool = ROOT / 'scripts' / 'source_integrity.py'
    spec = importlib.util.spec_from_file_location('mte_source_integrity_recovery', tool)
    if spec is None or spec.loader is None:
        raise RecoveryError('could not load source-integrity module')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _workflow_set_sha256(root: Path, contract: dict[str, Any]) -> str:
    paths = ((contract.get('repositoryOnboarding') or {}).get('expectedWorkflowPaths') or [])
    if not isinstance(paths, list) or not paths:
        raise RecoveryError('production contract has no expected workflow path set')
    manifest: dict[str, str] = {}
    for rel in paths:
        rel = str(rel)
        path = root / rel
        if not path.is_file() or path.is_symlink():
            raise RecoveryError(f'expected production workflow is missing/symlinked: {rel}')
        manifest[rel] = sha256_file(path)
    return sha256_bytes(canonical(manifest))


def _normalize_origin_url(url: str) -> str | None:
    text = url.strip()
    if text.endswith('.git'):
        text = text[:-4]
    if text.startswith('git@github.com:'):
        return text[len('git@github.com:'):]
    for prefix in ('https://github.com/', 'ssh://git@github.com/'):
        if text.startswith(prefix):
            return text[len(prefix):]
    return None


def _git(checkout: Path, *args: str) -> str:
    proc = subprocess.run(['git', *args], cwd=checkout, text=True, capture_output=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()[:500]
        raise RecoveryError(f'git {" ".join(args)} failed in restore checkout: {detail}')
    return proc.stdout.strip()


def _verify_source_tree(root: Path, expected_manifest: Path) -> str:
    local = root / 'SOURCE_SHA256SUMS.txt'
    if not local.is_file() or local.is_symlink():
        raise RecoveryError('restore checkout is missing SOURCE_SHA256SUMS.txt')
    if local.read_bytes() != expected_manifest.read_bytes():
        raise RecoveryError('restore checkout SOURCE_SHA256SUMS.txt differs from the recovery bundle')
    module = _load_source_integrity_module()
    errors = module.verify_source_integrity(root)
    if errors:
        raise RecoveryError('restore checkout Source Integrity failed: ' + '; '.join(errors[:8]))
    return sha256_file(local)


def _verify_checkout_identity(checkout: Path, ledger: dict[str, Any], contract: dict[str, Any], bundle_root: Path) -> dict[str, str]:
    checkout = checkout.resolve()
    if not (checkout / '.git').exists():
        raise RecoveryError('restore target must be a real Git checkout with .git metadata')
    head = _git(checkout, 'rev-parse', 'HEAD').lower()
    if head != str(ledger.get('currentSourceHeadSha', '')).lower():
        raise RecoveryError(f'restore checkout HEAD differs from recovery source cursor: local={head} bundle={ledger.get("currentSourceHeadSha")}')
    branch = _git(checkout, 'branch', '--show-current')
    if branch != str(ledger.get('defaultBranch', '')):
        raise RecoveryError(f'restore checkout branch must be the sealed default branch {ledger.get("defaultBranch")!r}, got {branch!r}')
    origin = _normalize_origin_url(_git(checkout, 'remote', 'get-url', 'origin'))
    if origin is None or origin.lower() != str(ledger.get('repository', '')).lower():
        raise RecoveryError(f'restore checkout origin differs from sealed repository identity: {origin!r}')
    if subprocess.run(['git', 'diff', '--quiet'], cwd=checkout).returncode != 0 or subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=checkout).returncode != 0:
        raise RecoveryError('restore checkout has tracked/staged modifications; use a clean checkout at the exact recovery commit')
    untracked = _git(checkout, 'ls-files', '--others', '--exclude-standard').splitlines()
    unsafe_untracked = [x for x in untracked if x and not (x == 'first-real-run-ledger.json' or x == '.mte-production-bootstrap.json' or x.startswith('release/'))]
    if unsafe_untracked:
        raise RecoveryError(f'restore checkout has unexpected untracked source paths: {unsafe_untracked[:8]}')
    target_contract = checkout / 'release-control' / 'production-execution-contract.json'
    bundled_contract = bundle_root / 'production-execution-contract.json'
    if not target_contract.is_file() or target_contract.read_bytes() != bundled_contract.read_bytes():
        raise RecoveryError('restore checkout production execution contract differs from the recovery bundle')
    target_contract_sha = sha256_file(target_contract)
    if target_contract_sha != str(ledger.get('contractSha256', '')):
        raise RecoveryError('restore checkout contract SHA-256 differs from the sealed ledger contract')
    workflow_sha = _workflow_set_sha256(checkout, contract)
    if workflow_sha != str(ledger.get('workflowSetSha256', '')):
        raise RecoveryError('restore checkout production workflow-set hash differs from the sealed ledger')
    source_manifest_sha = _verify_source_tree(checkout, bundle_root / 'SOURCE_SHA256SUMS.txt')
    return {'headSha': head, 'defaultBranch': branch, 'workflowSetSha256': workflow_sha, 'sourceIntegrityManifestSha256': source_manifest_sha}


def _safe_extract_bundle(path: Path, destination: Path) -> None:
    with zipfile.ZipFile(path) as zf:
        seen: set[str] = set()
        for info in zf.infolist():
            name = info.filename
            if '\\' in name or '\x00' in name:
                raise RecoveryError('recovery bundle contains a non-portable archive path')
            pp = Path(name)
            if info.is_dir():
                continue
            if name.startswith('/') or pp.is_absolute() or '..' in pp.parts or any(part in {'', '.'} for part in pp.parts):
                raise RecoveryError('recovery bundle contains an unsafe archive path')
            if name in seen:
                raise RecoveryError(f'recovery bundle contains duplicate archive member: {name}')
            seen.add(name)
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise RecoveryError('recovery bundle contains a symlink')
            target = destination / pp
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, 'r') as src, target.open('wb') as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)


def _verify_extracted_bundle(temp: Path, bundle_path: Path | None = None) -> dict[str, Any]:
    manifest_path = temp / 'RECOVERY_BUNDLE_MANIFEST.json'
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise RecoveryError('recovery bundle manifest is missing')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('schemaVersion') != 2 or manifest.get('revision') != BUNDLE_REVISION or manifest.get('manifestSha256') != _manifest_hash(manifest):
        raise RecoveryError('recovery bundle manifest is invalid')
    listed_items = manifest.get('files') or []
    if not isinstance(listed_items, list):
        raise RecoveryError('recovery bundle file manifest is invalid')
    listed = {str(x.get('path', '')): x for x in listed_items}
    if len(listed) != len(listed_items):
        raise RecoveryError('recovery bundle file manifest contains duplicate paths')
    actual: dict[str, Path] = {}
    for p in temp.rglob('*'):
        if p.is_symlink():
            raise RecoveryError('recovery bundle extraction contains a symlink')
        if p.is_file() and p.name != 'RECOVERY_BUNDLE_MANIFEST.json':
            actual[p.relative_to(temp).as_posix()] = p
    if set(listed) != set(actual):
        raise RecoveryError(f'recovery bundle file set differs from manifest; extra={sorted(set(actual)-set(listed))}, missing={sorted(set(listed)-set(actual))}')
    for rel, p in actual.items():
        item = listed[rel]
        if p.stat().st_size != int(item.get('sizeBytes', -1)) or sha256_file(p) != str(item.get('sha256', '')):
            raise RecoveryError(f'recovery bundle file mismatch: {rel}')
    ledger_path = temp / 'ledger.json'
    contract_path = temp / 'production-execution-contract.json'
    source_manifest = temp / 'SOURCE_SHA256SUMS.txt'
    if not ledger_path.is_file() or not contract_path.is_file() or not source_manifest.is_file():
        raise RecoveryError('recovery bundle is missing ledger/contract/source-integrity material')
    ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    H = _load_handoff_module()
    try:
        H.validate(ledger, contract, contract_path)
    except Exception as exc:
        raise RecoveryError(f'recovery bundle ledger is invalid: {exc}') from exc
    if str(manifest.get('releaseId')) != str(ledger.get('releaseId')) or str(manifest.get('releaseClass')) != str(ledger.get('releaseClass')):
        raise RecoveryError('recovery bundle release identity differs from the sealed ledger')
    if str(manifest.get('repository')) != str(ledger.get('repository')) or str(manifest.get('repositoryId')) != str(ledger.get('repositoryId')):
        raise RecoveryError('recovery bundle repository identity differs from the sealed ledger')
    if str(manifest.get('defaultBranch')) != str(ledger.get('defaultBranch')) or str(manifest.get('currentSourceHeadSha')) != str(ledger.get('currentSourceHeadSha')):
        raise RecoveryError('recovery bundle source cursor differs from the sealed ledger')
    if str(manifest.get('workflowSetSha256')) != str(ledger.get('workflowSetSha256')):
        raise RecoveryError('recovery bundle workflow-set binding differs from the sealed ledger')
    if str(manifest.get('contractSha256')) != sha256_file(contract_path) or str(manifest.get('contractSha256')) != str(ledger.get('contractSha256')):
        raise RecoveryError('recovery bundle contract hash binding is invalid')
    if str(manifest.get('sourceIntegrityManifestSha256')) != sha256_file(source_manifest):
        raise RecoveryError('recovery bundle Source Integrity manifest hash binding is invalid')
    if str(manifest.get('originalLedgerSha256')) != sha256_file(ledger_path):
        raise RecoveryError('recovery bundle original ledger file hash binding is invalid')
    summary_stages: list[str] = []
    for record in ledger.get('records') or []:
        summary = record.get('recoverySnapshot')
        if not isinstance(summary, dict):
            continue
        stage = str(record.get('stage', ''))
        stage_dir = temp / 'snapshots' / safe_name(stage)
        snap = verify_snapshot_dir(stage_dir)
        if snap.get('manifestSha256') != summary.get('manifestSha256') or snap.get('stage') != stage:
            raise RecoveryError(f'bundled recovery snapshot identity mismatch for stage {stage}')
        if snap.get('testOnly') is True:
            raise RecoveryError(f'bundled recovery snapshot is test-only: {stage}')
        summary_stages.append(stage)
    if list(manifest.get('snapshotStages') or []) != summary_stages:
        raise RecoveryError('recovery bundle snapshot-stage order differs from the sealed ledger')
    next_stage = H.next_stage(ledger, contract)
    records = ledger.get('records') or []
    last_stage = str(records[-1].get('stage')) if records else None
    if manifest.get('lastCompletedStage') != last_stage or manifest.get('nextStage') != next_stage:
        raise RecoveryError('recovery bundle last/next-stage binding differs from the sealed ledger')
    return manifest


def export_bundle(*, ledger_path: Path, contract_path: Path, output: Path) -> dict[str, Any]:
    ledger_path = ledger_path.resolve()
    contract_path = contract_path.resolve()
    source_root = contract_path.parent.parent
    ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    H = _load_handoff_module()
    try:
        H.validate(ledger, contract, contract_path)
        verify_ledger_recovery(ledger, contract)
    except Exception as exc:
        raise RecoveryError(f'ledger/recovery chain is not exportable: {exc}') from exc
    workflow_sha = _workflow_set_sha256(source_root, contract)
    if workflow_sha != str(ledger.get('workflowSetSha256', '')):
        raise RecoveryError('source workflow-set hash differs from the sealed ledger; export from the exact current checkout')
    source_manifest = source_root / 'SOURCE_SHA256SUMS.txt'
    source_integrity_sha = _verify_source_tree(source_root, source_manifest)
    snapshots: list[tuple[str, Path, dict[str, Any]]] = []
    for record in ledger.get('records') or []:
        summary = record.get('recoverySnapshot')
        if not isinstance(summary, dict):
            continue
        stage = str(record['stage'])
        manifest = verify_summary(summary, stage=stage, expected_run_ids=[str(x.get('runId')) for x in record.get('runObservations') or []] if record.get('runObservations') else None, source_head_sha=str(record.get('sourceHeadShaBefore', '')))
        if manifest.get('testOnly') is True:
            raise RecoveryError(f'cannot export production recovery bundle with test-only snapshot: {stage}')
        snapshots.append((stage, snapshot_path_from_summary(summary), manifest))
    if not snapshots:
        raise RecoveryError('ledger has no recovery snapshots to export')
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.mte-recovery-bundle.', dir=output.parent))
    try:
        shutil.copyfile(ledger_path, temp / 'ledger.json')
        shutil.copyfile(contract_path, temp / 'production-execution-contract.json')
        shutil.copyfile(source_manifest, temp / 'SOURCE_SHA256SUMS.txt')
        for stage, stage_dir, _ in snapshots:
            shutil.copytree(stage_dir, temp / 'snapshots' / safe_name(stage))
        files = []
        for p in sorted(x for x in temp.rglob('*') if x.is_file()):
            rel = p.relative_to(temp).as_posix()
            files.append({'path': rel, 'sizeBytes': p.stat().st_size, 'sha256': sha256_file(p)})
        records = ledger.get('records') or []
        bundle_manifest = {
            'schemaVersion': 2, 'revision': BUNDLE_REVISION,
            'releaseId': ledger['releaseId'], 'releaseClass': ledger['releaseClass'],
            'repository': ledger['repository'], 'repositoryId': str(ledger['repositoryId']),
            'defaultBranch': ledger['defaultBranch'], 'currentSourceHeadSha': ledger['currentSourceHeadSha'],
            'workflowSetSha256': ledger['workflowSetSha256'], 'contractSha256': sha256_file(contract_path),
            'sourceIntegrityManifestSha256': source_integrity_sha, 'originalLedgerSha256': sha256_file(ledger_path),
            'lastCompletedStage': str(records[-1].get('stage')) if records else None,
            'nextStage': H.next_stage(ledger, contract), 'createdAt': now_iso(),
            'snapshotStages': [x[0] for x in snapshots], 'files': files,
            'notice': 'Portable operational recovery bundle. It preserves existing provenance/evidence bytes and does not create release evidence.',
        }
        bundle_manifest['manifestSha256'] = _manifest_hash(bundle_manifest)
        _write_json(temp / 'RECOVERY_BUNDLE_MANIFEST.json', bundle_manifest)
        _verify_extracted_bundle(temp)
        if output.exists():
            output.unlink()
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for p in sorted(x for x in temp.rglob('*') if x.is_file()):
                zf.write(p, p.relative_to(temp).as_posix())
        return {'passed': True, 'output': str(output), 'sha256': sha256_file(output), 'snapshotCount': len(snapshots), 'manifestSha256': bundle_manifest['manifestSha256'], 'nextStage': bundle_manifest['nextStage']}
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def verify_bundle(path: Path) -> dict[str, Any]:
    path = path.resolve()
    if not zipfile.is_zipfile(path):
        raise RecoveryError('recovery bundle is not a ZIP archive')
    temp = Path(tempfile.mkdtemp(prefix='.mte-recovery-verify.'))
    try:
        _safe_extract_bundle(path, temp)
        manifest = _verify_extracted_bundle(temp, path)
        return {'passed': True, 'sha256': sha256_file(path), 'manifestSha256': manifest['manifestSha256'], 'snapshotCount': len(manifest.get('snapshotStages') or []), 'releaseId': manifest.get('releaseId'), 'releaseClass': manifest.get('releaseClass'), 'repository': manifest.get('repository'), 'repositoryId': manifest.get('repositoryId'), 'currentSourceHeadSha': manifest.get('currentSourceHeadSha'), 'originalLedgerSha256': manifest.get('originalLedgerSha256'), 'lastCompletedStage': manifest.get('lastCompletedStage'), 'nextStage': manifest.get('nextStage')}
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def _rewrite_ledger_for_restore(ledger: dict[str, Any], restore_rel: Path, contract: dict[str, Any]) -> dict[str, Any]:
    value = json.loads(json.dumps(ledger))
    for record in value.get('records') or []:
        summary = record.get('recoverySnapshot')
        if isinstance(summary, dict):
            summary['relativePath'] = (restore_rel / 'recovery' / safe_name(str(record.get('stage', '')))).as_posix()
    H = _load_handoff_module()
    return H.seal(value)


def _build_restore_catalog(staging: Path, ledger: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    manuals: list[dict[str, Any]] = []
    for record in ledger.get('records') or []:
        stage = str(record.get('stage', ''))
        summary = record.get('recoverySnapshot')
        if not isinstance(summary, dict):
            continue
        snap_root = staging / 'recovery' / safe_name(stage)
        manifest = verify_snapshot_dir(snap_root)
        if manifest.get('kind') == 'automated-stage':
            for run in manifest.get('runSummaries') or []:
                run_id = str(run.get('runId', ''))
                meta_path = snap_root / 'runs' / run_id / 'artifacts.json'
                payload = json.loads(meta_path.read_text(encoding='utf-8')) if meta_path.is_file() else {'artifacts': []}
                for item in payload.get('artifacts') or []:
                    rel = Path('recovery') / safe_name(stage) / str(item['archivePath'])
                    artifacts.append({
                        'stage': stage, 'runId': run_id, 'artifactId': int(item['id']), 'artifactName': item['name'],
                        'archivePath': rel.as_posix(), 'archiveSha256': item['archiveSha256'],
                        'expiresAtOriginalGitHub': item.get('expiresAt'), 'githubDigest': item.get('githubDigest'),
                    })
        if manifest.get('kind') == 'manual-stage':
            source_manual = snap_root / 'manual'
            if source_manual.is_dir():
                target_manual = staging / 'manual' / safe_name(stage)
                shutil.copytree(source_manual, target_manual)
            for item in manifest.get('manualEvidence') or []:
                manuals.append({
                    'stage': stage, 'role': item['role'], 'sourceFileName': item['sourceFileName'],
                    'restoredPath': (Path('manual') / safe_name(stage) / Path(str(item['archivePath'])).relative_to('manual')).as_posix(),
                    'sha256': item['sha256'], 'sizeBytes': item['sizeBytes'],
                })
    return ({'schemaVersion': 1, 'revision': RESTORE_REVISION, 'artifacts': artifacts}, {'schemaVersion': 1, 'revision': RESTORE_REVISION, 'manualEvidence': manuals})


def _restore_manifest_hash(value: dict[str, Any]) -> str:
    body = dict(value)
    body.pop('manifestSha256', None)
    return sha256_bytes(canonical(body))


def _verify_restore_root(checkout: Path, restore_root: Path, *, verify_checkout: bool = True) -> dict[str, Any]:
    checkout = checkout.resolve()
    restore_root = restore_root.resolve()
    manifest_path = restore_root / 'RESTORE_MANIFEST.json'
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise RecoveryError('rehydrated restore manifest is missing')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('schemaVersion') != 1 or manifest.get('revision') != RESTORE_REVISION or manifest.get('manifestSha256') != _restore_manifest_hash(manifest):
        raise RecoveryError('rehydrated restore manifest is invalid')
    listed_items = manifest.get('files') or []
    listed = {str(x.get('path', '')): x for x in listed_items}
    if len(listed) != len(listed_items):
        raise RecoveryError('rehydrated restore manifest contains duplicate file paths')
    actual: dict[str, Path] = {}
    for p in restore_root.rglob('*'):
        if p.is_symlink():
            raise RecoveryError('rehydrated restore tree contains a symlink')
        if p.is_file() and p.name != 'RESTORE_MANIFEST.json':
            actual[p.relative_to(restore_root).as_posix()] = p
    if set(actual) != set(listed):
        raise RecoveryError(f'rehydrated restore file set differs from manifest; extra={sorted(set(actual)-set(listed))}, missing={sorted(set(listed)-set(actual))}')
    for rel, p in actual.items():
        item = listed[rel]
        if p.stat().st_size != int(item.get('sizeBytes', -1)) or sha256_file(p) != str(item.get('sha256', '')):
            raise RecoveryError(f'rehydrated restore file mismatch: {rel}')
    ledger_path = restore_root / 'ledger.json'
    contract_path = checkout / 'release-control' / 'production-execution-contract.json'
    ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    H = _load_handoff_module()
    try:
        H.validate(ledger, contract, contract_path)
    except Exception as exc:
        raise RecoveryError(f'rehydrated ledger validation failed: {exc}') from exc
    verified: dict[str, str] = {}
    automated = {'workflow', 'workflow-set'}
    manual = set(contract['firstRealRun'].get('manualReviewBoundaries') or [])
    for record in ledger.get('records') or []:
        stage = str(record.get('stage', ''))
        hint = (contract['firstRealRun'].get('stageLaunchHints') or {}).get(stage) or {}
        if hint.get('kind') not in automated and stage not in manual:
            continue
        summary = record.get('recoverySnapshot')
        ref = record.get('recoverySnapshotRef')
        if isinstance(summary, dict):
            path = Path(str(summary.get('relativePath', '')))
            if path.is_absolute() or '..' in path.parts:
                raise RecoveryError(f'rehydrated ledger contains unsafe recovery path for {stage}')
            snap = verify_snapshot_dir(checkout / path)
            if snap.get('manifestSha256') != summary.get('manifestSha256') or snap.get('stage') != stage or snap.get('testOnly') is True:
                raise RecoveryError(f'rehydrated recovery snapshot binding failed for {stage}')
            run_ids = [str(x.get('runId')) for x in record.get('runObservations') or []] if hint.get('kind') in automated else []
            if list(snap.get('runIds') or []) != run_ids or str(snap.get('sourceHeadSha')) != str(record.get('sourceHeadShaBefore')):
                raise RecoveryError(f'rehydrated recovery run/source binding failed for {stage}')
            verified[stage] = str(snap['manifestSha256'])
        elif isinstance(ref, dict):
            source_stage = str(ref.get('stage', ''))
            if verified.get(source_stage) != str(ref.get('manifestSha256', '')):
                raise RecoveryError(f'rehydrated recovery reference failed for {stage}')
            verified[stage] = verified[source_stage]
        else:
            raise RecoveryError(f'rehydrated ledger is missing recovery state for {stage}')
    if str(manifest.get('repository')) != str(ledger.get('repository')) or str(manifest.get('repositoryId')) != str(ledger.get('repositoryId')):
        raise RecoveryError('rehydrated restore repository identity differs from ledger')
    if str(manifest.get('currentSourceHeadSha')) != str(ledger.get('currentSourceHeadSha')) or str(manifest.get('workflowSetSha256')) != str(ledger.get('workflowSetSha256')):
        raise RecoveryError('rehydrated restore source/workflow binding differs from ledger')
    if str(manifest.get('restoredLedgerSha256')) != sha256_file(ledger_path):
        raise RecoveryError('rehydrated restore ledger file hash differs from restore manifest')
    if verify_checkout:
        bundle_source_manifest = restore_root / 'bundle-source-integrity' / 'SOURCE_SHA256SUMS.txt'
        bundle_contract = restore_root / 'bundle-source-integrity' / 'production-execution-contract.json'
        if not bundle_source_manifest.is_file() or not bundle_contract.is_file():
            raise RecoveryError('rehydrated restore is missing its source-integrity/contract witness copies')
        if (checkout / 'release-control' / 'production-execution-contract.json').read_bytes() != bundle_contract.read_bytes():
            raise RecoveryError('current checkout contract differs from the restored contract witness')
        source_sha = _verify_source_tree(checkout, bundle_source_manifest)
        if source_sha != str(manifest.get('sourceIntegrityManifestSha256')):
            raise RecoveryError('current checkout Source Integrity manifest differs from restore provenance')
        head = _git(checkout, 'rev-parse', 'HEAD').lower()
        branch = _git(checkout, 'branch', '--show-current')
        origin = _normalize_origin_url(_git(checkout, 'remote', 'get-url', 'origin'))
        if head != str(ledger.get('currentSourceHeadSha')).lower() or branch != str(ledger.get('defaultBranch')) or origin is None or origin.lower() != str(ledger.get('repository')).lower():
            raise RecoveryError('current checkout git identity/cursor differs from the rehydrated ledger')
        if _workflow_set_sha256(checkout, contract) != str(ledger.get('workflowSetSha256')):
            raise RecoveryError('current checkout workflow-set differs from the rehydrated ledger')
    return {'passed': True, 'restoreRoot': str(restore_root), 'restoreManifestSha256': manifest['manifestSha256'], 'bundleSha256': manifest['bundleSha256'], 'ledger': str(ledger_path), 'completedStageCount': len(ledger.get('records') or []), 'nextStage': H.next_stage(ledger, contract)}


def restore_bundle(*, bundle: Path, checkout: Path, output: Path | None = None) -> dict[str, Any]:
    bundle = bundle.resolve()
    checkout = checkout.resolve()
    if not zipfile.is_zipfile(bundle):
        raise RecoveryError('recovery bundle is not a ZIP archive')
    extracted = Path(tempfile.mkdtemp(prefix='.mte-recovery-restore-bundle.'))
    try:
        _safe_extract_bundle(bundle, extracted)
        bundle_manifest = _verify_extracted_bundle(extracted, bundle)
        ledger = json.loads((extracted / 'ledger.json').read_text(encoding='utf-8'))
        contract = json.loads((extracted / 'production-execution-contract.json').read_text(encoding='utf-8'))
        identity = _verify_checkout_identity(checkout, ledger, contract, extracted)
        bundle_sha = sha256_file(bundle)
        default_rel = Path('release') / 'rehydrated' / f'{safe_name(str(ledger["releaseId"]))}-{bundle_sha[:12]}'
        final = (checkout / default_rel).resolve() if output is None else (output.resolve() if output.is_absolute() else (checkout / output).resolve())
        release_root = (checkout / 'release').resolve()
        try:
            final.relative_to(release_root)
        except ValueError as exc:
            raise RecoveryError('rehydrated restore output must stay under the checkout release/ directory') from exc
        if final == release_root:
            raise RecoveryError('rehydrated restore output cannot replace the release/ directory itself')
        restore_rel = final.relative_to(checkout)
        if final.exists():
            existing = _verify_restore_root(checkout, final, verify_checkout=True)
            if existing.get('bundleSha256') != bundle_sha:
                raise RecoveryError('restore destination already exists for a different recovery bundle')
            existing['idempotent'] = True
            return existing
        final.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f'.{final.name}.staging-', dir=final.parent))
        try:
            for stage in bundle_manifest.get('snapshotStages') or []:
                shutil.copytree(extracted / 'snapshots' / safe_name(str(stage)), staging / 'recovery' / safe_name(str(stage)))
            restored_ledger = _rewrite_ledger_for_restore(ledger, restore_rel, contract)
            _write_json(staging / 'ledger.json', restored_ledger)
            artifacts, manuals = _build_restore_catalog(staging, restored_ledger)
            _write_json(staging / 'artifact-catalog.json', artifacts)
            _write_json(staging / 'manual-catalog.json', manuals)
            witness = staging / 'bundle-source-integrity'
            witness.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(extracted / 'SOURCE_SHA256SUMS.txt', witness / 'SOURCE_SHA256SUMS.txt')
            shutil.copyfile(extracted / 'production-execution-contract.json', witness / 'production-execution-contract.json')
            for stage in bundle_manifest.get('snapshotStages') or []:
                verify_snapshot_dir(staging / 'recovery' / safe_name(str(stage)))
            H = _load_handoff_module()
            try:
                H.validate(restored_ledger, contract, checkout / 'release-control' / 'production-execution-contract.json')
            except Exception as exc:
                raise RecoveryError(f'rehydrated ledger is invalid before commit: {exc}') from exc
            files = []
            for p in sorted(x for x in staging.rglob('*') if x.is_file() and x.name != 'RESTORE_MANIFEST.json'):
                rel = p.relative_to(staging).as_posix()
                files.append({'path': rel, 'sizeBytes': p.stat().st_size, 'sha256': sha256_file(p)})
            restore_manifest = {
                'schemaVersion': 1, 'revision': RESTORE_REVISION,
                'bundleSha256': bundle_sha, 'bundleManifestSha256': bundle_manifest['manifestSha256'],
                'originalLedgerSha256': bundle_manifest['originalLedgerSha256'], 'restoredLedgerSha256': sha256_file(staging / 'ledger.json'),
                'releaseId': ledger['releaseId'], 'releaseClass': ledger['releaseClass'],
                'repository': ledger['repository'], 'repositoryId': str(ledger['repositoryId']), 'defaultBranch': ledger['defaultBranch'],
                'currentSourceHeadSha': ledger['currentSourceHeadSha'], 'workflowSetSha256': identity['workflowSetSha256'],
                'sourceIntegrityManifestSha256': identity['sourceIntegrityManifestSha256'],
                'lastCompletedStage': bundle_manifest.get('lastCompletedStage'), 'nextStage': bundle_manifest.get('nextStage'),
                'restoredAt': now_iso(), 'files': files,
                'notice': 'Operational restore provenance only. Rehydration preserves prior evidence/recovery bytes and cannot satisfy release gates by itself.',
            }
            restore_manifest['manifestSha256'] = _restore_manifest_hash(restore_manifest)
            _write_json(staging / 'RESTORE_MANIFEST.json', restore_manifest)
            # Single-directory atomic activation: no partial release state is exposed.
            os.replace(staging, final)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        result = _verify_restore_root(checkout, final, verify_checkout=True)
        result['idempotent'] = False
        return result
    finally:
        shutil.rmtree(extracted, ignore_errors=True)


def verify_restored(*, checkout: Path, restore_root: Path) -> dict[str, Any]:
    return _verify_restore_root(checkout.resolve(), restore_root.resolve(), verify_checkout=True)


def main() -> int:
    parser = argparse.ArgumentParser(description='Content-addressed disaster-recovery capture, export, restore and offline verification for the first real production run.')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('export')
    p.add_argument('--ledger', type=Path, required=True)
    p.add_argument('--contract', type=Path, default=DEFAULT_CONTRACT)
    p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('verify-bundle')
    p.add_argument('--bundle', type=Path, required=True)
    p = sub.add_parser('restore')
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--checkout', type=Path, required=True)
    p.add_argument('--output', type=Path, help='Optional restore directory; must remain under CHECKOUT/release/. Default is content-addressed under release/rehydrated/.')
    p = sub.add_parser('verify-restored')
    p.add_argument('--checkout', type=Path, required=True)
    p.add_argument('--restore-root', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'export':
            result = export_bundle(ledger_path=args.ledger.resolve(), contract_path=args.contract.resolve(), output=args.output)
        elif args.command == 'verify-bundle':
            result = verify_bundle(args.bundle)
        elif args.command == 'restore':
            result = restore_bundle(bundle=args.bundle, checkout=args.checkout, output=args.output)
        else:
            result = verify_restored(checkout=args.checkout, restore_root=args.restore_root)
        print(json.dumps(result, indent=2))
        return 0
    except RecoveryError as exc:
        print(json.dumps({'passed': False, 'error': str(exc)}, indent=2))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
