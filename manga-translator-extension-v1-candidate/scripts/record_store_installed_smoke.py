from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from release_evidence import load_json, require_hex64, sha256_file, validate_controlled_manifest
from v1_evidence_orchestrator import read_session, read_store_handoff, require_release_identity


def chrome_version(executable: Path) -> str:
    output = subprocess.check_output([str(executable), '--version'], text=True, stderr=subprocess.STDOUT, timeout=15).strip()
    match = re.search(r'(\d+(?:\.\d+){1,3})', output)
    if not match:
        raise RuntimeError(f'could not parse Chrome version from: {output}')
    return match.group(1)


def confirm(prompt: str) -> None:
    answer = input(f'{prompt} Type YES to attest this check: ').strip()
    if answer != 'YES':
        raise RuntimeError('Store-installed browser smoke aborted; no evidence was written')


def main() -> int:
    parser = argparse.ArgumentParser(description='Interactive Store-installed smoke bound to the exact controlled Store candidate.')
    parser.add_argument('--controlled-manifest', type=Path, required=True)
    parser.add_argument('--orchestration-session', type=Path, required=True, help='evidence-promoted public-v1 checkpoint')
    parser.add_argument('--store-submission-handoff', type=Path, required=True)
    parser.add_argument('--store-candidate', type=Path, required=True)
    parser.add_argument('--chrome', type=Path, required=True)
    parser.add_argument('--expected-major', type=int, required=True)
    parser.add_argument('--engine-target', choices=('linux-x86_64', 'macos-arm64', 'windows-x86_64'), required=True)
    parser.add_argument('--store-item-id', required=True)
    parser.add_argument('--fixture-url', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()

    if not sys.stdin.isatty():
        raise SystemExit('Store-installed acceptance is intentionally interactive; run it on a clean GUI machine with a TTY')
    if not re.fullmatch(r'[a-p]{32}', args.store_item_id):
        raise SystemExit('Chrome Web Store item id must be 32 lowercase a-p characters')
    if args.expected_major < 148:
        raise SystemExit('Store-installed release smoke refuses Chrome older than baseline 148')
    if not re.fullmatch(r'https?://(?:127\.0\.0\.1|localhost)(?::\d+)?(?:/.*)?', args.fixture_url):
        raise SystemExit('Store-installed smoke fixture must be local 127.0.0.1/localhost HTTP(S)')

    manifest_path = args.controlled_manifest.resolve()
    manifest, manifest_sha = validate_controlled_manifest(manifest_path, require_v1=True)
    if manifest.get('releaseClass') != 'public-v1':
        raise SystemExit('Store-installed smoke requires a public-v1 controlled manifest')
    orchestration = read_session(args.orchestration_session.resolve(), 'evidence-promoted')
    if orchestration.get('releaseClass') != 'public-v1':
        raise SystemExit('Store-installed smoke requires a public-v1 evidence-promoted orchestration session')
    require_release_identity(orchestration, manifest, manifest_sha)
    handoff = read_store_handoff(args.store_submission_handoff.resolve())
    if handoff.get('orchestrationSessionSha256') != orchestration.get('sessionSha256') or handoff.get('controlledManifestSha256') != manifest_sha:
        raise SystemExit('Store submission handoff is not bound to this orchestration/controlled manifest')

    candidate = load_json(args.store_candidate.resolve(), 'Store candidate metadata')
    extension = manifest.get('extension') if isinstance(manifest.get('extension'), dict) else {}
    expected_sha = require_hex64(extension.get('sha256'), 'controlled Extension sha256')
    if candidate.get('schemaVersion') != 2 or candidate.get('controlledManifestSha256') != manifest_sha:
        raise SystemExit('Store candidate metadata is not the controlled public-v1 candidate schema')
    if candidate.get('storeSubmissionHandoffSha256') != handoff.get('handoffSha256'):
        raise SystemExit('Store candidate metadata is not bound to this Store handoff')
    if require_hex64(candidate.get('sha256'), 'Store candidate sha256') != expected_sha:
        raise SystemExit('Store candidate hash differs from the controlled Extension')
    candidate_zip = args.store_candidate.resolve().parent / str(candidate.get('artifact'))
    if not candidate_zip.is_file() or sha256_file(candidate_zip) != expected_sha:
        raise SystemExit('exact Store candidate ZIP is missing or hash-mismatched')

    engine_entry = next((item for item in manifest.get('engines', []) if isinstance(item, dict) and item.get('target') == args.engine_target), None)
    if not isinstance(engine_entry, dict):
        raise SystemExit(f'controlled manifest has no Engine artifact for {args.engine_target}')
    engine_sha = require_hex64(engine_entry.get('sha256'), 'controlled Engine sha256')

    chrome = args.chrome.resolve()
    if not chrome.is_file():
        raise SystemExit('Chrome executable does not exist')
    version = chrome_version(chrome)
    major = int(version.split('.', 1)[0])
    if major != args.expected_major:
        raise SystemExit(f'Chrome major mismatch: expected {args.expected_major}, got {version}')

    with tempfile.TemporaryDirectory(prefix=f'mte-store-chrome-{major}-') as temp_raw:
        profile_dir = Path(temp_raw) / 'chrome-profile'
        store_url = f'https://chromewebstore.google.com/detail/{args.store_item_id}'
        proc = subprocess.Popen([
            str(chrome),
            f'--user-data-dir={profile_dir}',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-sync',
            store_url,
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            time.sleep(2)
            if proc.poll() is not None:
                raise RuntimeError('Chrome exited before Store-installed smoke began')
            print(f'Controlled manifest: sha256:{manifest_sha}')
            print(f'Store candidate: {candidate_zip.name} sha256:{expected_sha}')
            print(f'Chrome: {version}; clean temporary profile: {profile_dir}')
            print(f'Chrome Web Store item: {args.store_item_id}; expected extension version: {extension.get("manifestVersion")}')
            print(f'Exact Local Engine to use: {args.engine_target} / {engine_entry.get("artifact")} / sha256:{engine_sha}')
            confirm('STORE INSTALL — install the staged/published Store item into this clean profile and confirm its displayed version matches the controlled candidate.')
            confirm('ACTIVATE — confirm first-run privacy consent and explicit page activation reach Ready on the authorized local fixture.')
            confirm('TRANSLATE — confirm the local fixture translates through the exact controlled Engine and SFX remain preserved.')
            confirm('RESTORE — confirm Originals/restore returns the fixture to its original raster.')
            observation = {
                'schemaVersion': 2,
                'id': f'store-chrome-{major}-{manifest_sha[:16]}',
                'artifactManifestSha256': manifest_sha,
                'orchestrationSessionSha256': orchestration['sessionSha256'],
                'storeSubmissionHandoffSha256': handoff['handoffSha256'],
                'storeCandidateSha256': expected_sha,
                'storeItemId': args.store_item_id,
                'storeVersion': str(extension.get('manifestVersion')),
                'sourceHeadSha': manifest['sourceHeadSha'],
                'kind': 'store-installed-extension',
                'platform': 'browser',
                'artifact': extension.get('artifact'),
                'artifactSha256': expected_sha,
                'engineTargetAtTest': args.engine_target,
                'engineArtifactAtTest': engine_entry.get('artifact'),
                'engineArtifactSha256AtTest': engine_sha,
                'browserVersion': version,
                'testedAtUtc': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                'cleanEnvironment': True,
                'checks': {'install': True, 'activate': True, 'translateFixture': True, 'restore': True},
                'fixtureUrl': args.fixture_url,
                'evidenceMode': 'interactive-human-observed-store-installed-controlled-candidate',
                'notes': 'The tool bound the observation to the exact submitted controlled candidate, pre-Store handoff and clean Chrome profile. Store installation/version plus lifecycle checks are explicit human attestations.',
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(observation, indent=2) + '\n', encoding='utf-8')
            print(args.output)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
