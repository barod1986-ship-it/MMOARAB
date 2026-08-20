from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from release_evidence import load_json, sha256_file, validate_controlled_manifest, validate_smoke_observation
from source_integrity import parse_manifest, verify_source_integrity
from v1_evidence_orchestrator import read_session, read_store_handoff

ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR = ROOT / 'scripts' / 'v1_evidence_orchestrator.py'


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def run_checked(command: list[str]) -> None:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout, file=sys.stderr, end='')
        if result.stderr:
            print(result.stderr, file=sys.stderr, end='')
        raise SystemExit(result.returncode)


def render_integrity(staged_by_target: dict[Path, Path], source_manifest: Path) -> str:
    entries = parse_manifest(source_manifest)
    for target, staged in staged_by_target.items():
        rel = target.resolve().relative_to(ROOT).as_posix()
        entries[rel] = sha256_file(staged)
    return ''.join(f'{entries[rel]}  {rel}\n' for rel in sorted(entries))


def replace_transactionally(staged_by_target: dict[Path, Path], staged_manifest: Path, source_manifest: Path) -> None:
    backup = Path(tempfile.mkdtemp(prefix='mte-public-evidence-backup-'))
    targets = [*staged_by_target.keys(), source_manifest]
    try:
        saved: dict[Path, Path | None] = {}
        for target in targets:
            key = hashlib.sha256(str(target.resolve()).encode()).hexdigest()
            dst = backup / key
            if target.is_file():
                dst.write_bytes(target.read_bytes())
                saved[target] = dst
            else:
                saved[target] = None
        replaced: list[Path] = []
        try:
            for target, staged in staged_by_target.items():
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged, target)
                replaced.append(target)
            os.replace(staged_manifest, source_manifest)
            replaced.append(source_manifest)
            errors = verify_source_integrity(ROOT)
            if errors:
                raise RuntimeError('post-public-evidence source-integrity failed: ' + '; '.join(errors))
        except Exception:
            for target in reversed(replaced):
                src = saved[target]
                if src is None:
                    target.unlink(missing_ok=True)
                else:
                    target.write_bytes(src.read_bytes())
            raise
    finally:
        shutil.rmtree(backup, ignore_errors=True)


def browser_major(value: str) -> int:
    return int(value.split('.', 1)[0])


def main() -> int:
    parser = argparse.ArgumentParser(description='Transactionally promote post-Store public V1 evidence without rewriting pre-Store evidence truth.')
    parser.add_argument('--controlled-manifest', type=Path, required=True)
    parser.add_argument('--orchestration-session', type=Path, required=True, help='tracked evidence-promoted public-v1 checkpoint')
    parser.add_argument('--store-submission-handoff', type=Path, required=True)
    parser.add_argument('--store-candidate', type=Path, required=True)
    parser.add_argument('--store-observation', type=Path, action='append', default=[])
    parser.add_argument('--profile-privacy', type=Path, default=ROOT / 'store/release/profile-privacy.json')
    parser.add_argument('--records', type=Path, default=ROOT / 'release-control/smoke-records.json')
    parser.add_argument('--release-state', type=Path, default=ROOT / 'release-control/release-state.json')
    parser.add_argument('--publication-state', type=Path, default=ROOT / 'store/publication-state.json')
    parser.add_argument('--support-channels', type=Path, default=ROOT / 'release-control/support-channels.json')
    parser.add_argument('--production-downloads', type=Path, default=ROOT / 'release-control/production-downloads.json')
    parser.add_argument('--orchestration-output', type=Path, default=ROOT / 'release-control/v1-orchestration.json')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    if len(args.store_observation) != 2:
        raise SystemExit('public evidence promotion requires exactly two Store-installed observations (Chrome 148 and audited Stable)')
    manifest_path = args.controlled_manifest.resolve()
    manifest, manifest_sha = validate_controlled_manifest(manifest_path, require_v1=True)
    if manifest.get('releaseClass') != 'public-v1':
        raise SystemExit('post-Store promotion requires a public-v1 controlled manifest')
    session = read_session(args.orchestration_session.resolve(), 'evidence-promoted')
    if session.get('releaseClass') != 'public-v1' or session.get('controlled', {}).get('manifestSha256') != manifest_sha:
        raise SystemExit('evidence-promoted session is not bound to this public-v1 controlled manifest')
    handoff = read_store_handoff(args.store_submission_handoff.resolve())
    candidate = load_json(args.store_candidate.resolve(), 'Store candidate metadata')
    if handoff.get('orchestrationSessionSha256') != session.get('sessionSha256') or handoff.get('controlledManifestSha256') != manifest_sha:
        raise SystemExit('Store handoff is not bound to the evidence-promoted session')
    if candidate.get('controlledManifestSha256') != manifest_sha or candidate.get('storeSubmissionHandoffSha256') != handoff.get('handoffSha256'):
        raise SystemExit('Store candidate metadata is not bound to this Store handoff')

    records = load_json(args.records.resolve(), 'pre-Store smoke records')
    if records.get('controlledManifestSha256') != manifest_sha or not isinstance(records.get('records'), list):
        raise SystemExit('pre-Store smoke records are not bound to this controlled manifest')
    pre_records = records['records']
    if any(item.get('kind') == 'store-installed-extension' for item in pre_records if isinstance(item, dict)):
        raise SystemExit('pre-Store smoke records already contain Store-installed evidence; refusing ambiguous re-promotion')
    for item in pre_records:
        if not isinstance(item, dict):
            raise SystemExit('pre-Store smoke record entry is malformed')
        validate_smoke_observation(item, manifest=manifest, manifest_sha256=manifest_sha)

    state = load_json(args.release_state.resolve(), 'release state')
    audit = state.get('audit') if isinstance(state.get('audit'), dict) else {}
    baseline = int(audit.get('chromeBaselineMajor', 0))
    stable = int(audit.get('currentStableMajorAtAudit', 0))
    required = {baseline, stable}
    if 0 in required or len(required) != 2:
        raise SystemExit('release-state audit must define distinct Chrome baseline/current Stable majors')

    store_records: list[dict] = []
    seen: set[int] = set()
    for path in args.store_observation:
        item = load_json(path.resolve(), f'Store observation {path}')
        validate_smoke_observation(item, manifest=manifest, manifest_sha256=manifest_sha)
        if item.get('kind') != 'store-installed-extension':
            raise SystemExit('post-Store promotion accepts only store-installed-extension observations')
        if item.get('orchestrationSessionSha256') != session.get('sessionSha256'):
            raise SystemExit('Store-installed observation is not bound to the evidence-promoted orchestration session')
        if item.get('storeSubmissionHandoffSha256') != handoff.get('handoffSha256') or item.get('storeCandidateSha256') != candidate.get('sha256'):
            raise SystemExit('Store-installed observation is not bound to the exact approved Store candidate')
        major = browser_major(str(item.get('browserVersion')))
        if major in seen:
            raise SystemExit(f'duplicate Store-installed Chrome major: {major}')
        seen.add(major)
        store_records.append(item)
    if seen != required:
        raise SystemExit(f'Store-installed evidence must contain exactly Chrome majors {sorted(required)}')

    publication = load_json(args.publication_state.resolve(), 'Store publication state')
    # Manual/public facts remain operator-controlled. Only evidence-derived hash/smoke mirrors are changed here.
    with tempfile.TemporaryDirectory(prefix='mte-public-evidence-promotion-') as raw:
        stage = Path(raw)
        staged_records = stage / 'smoke-records.json'
        staged_state = stage / 'release-state.json'
        staged_publication = stage / 'publication-state.json'
        staged_orchestration = stage / 'v1-orchestration.json'
        staged_manifest = stage / 'SOURCE_SHA256SUMS.txt'

        merged = dict(records)
        merged['records'] = sorted([*pre_records, *store_records], key=lambda x: x['id'])
        write_json(staged_records, merged)

        state2 = json.loads(json.dumps(state))
        state2['releaseClass'] = 'public-v1'
        state2.setdefault('smoke', {})['storeInstalledVersionPassed'] = True
        write_json(staged_state, state2)

        publication2 = json.loads(json.dumps(publication))
        gates = publication2.setdefault('releaseGates', {})
        gates['chrome148StoreSmokePassed'] = 148 in seen
        gates['currentStableStoreSmokePassed'] = stable in seen
        gates['testedZipSha256'] = candidate.get('testedSha256')
        gates['storeCandidateZipSha256'] = candidate.get('sha256')
        write_json(staged_publication, publication2)

        run_checked([
            sys.executable, str(ORCHESTRATOR), 'public-promoted',
            '--session', str(args.orchestration_session.resolve()),
            '--controlled-manifest', str(manifest_path),
            '--profile-privacy', str(args.profile_privacy.resolve()),
            '--smoke-records', str(staged_records),
            '--release-state', str(staged_state),
            '--publication-state', str(staged_publication),
            '--support-channels', str(args.support_channels.resolve()),
            '--production-downloads', str(args.production_downloads.resolve()),
            '--store-candidate', str(args.store_candidate.resolve()),
            '--store-handoff', str(args.store_submission_handoff.resolve()),
            '--output', str(staged_orchestration),
        ])

        staged_by_target = {
            args.records.resolve(): staged_records,
            args.release_state.resolve(): staged_state,
            args.publication_state.resolve(): staged_publication,
            args.orchestration_output.resolve(): staged_orchestration,
        }
        source_manifest = ROOT / 'SOURCE_SHA256SUMS.txt'
        staged_manifest.write_text(render_integrity(staged_by_target, source_manifest), encoding='utf-8')
        if args.dry_run:
            print('post-Store public evidence validated; no source files changed')
            return 0
        replace_transactionally(staged_by_target, staged_manifest, source_manifest)

    print('post-Store public evidence promoted transactionally: two Store smokes + release/public state + orchestration + source integrity')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
