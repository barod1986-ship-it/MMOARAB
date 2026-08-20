from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from release_evidence import require_hex64, sha256_file, validate_controlled_manifest
from v1_evidence_orchestrator import read_session, require_release_identity


def chrome_version(executable: Path) -> str:
    output = subprocess.check_output([str(executable), '--version'], text=True, stderr=subprocess.STDOUT, timeout=15).strip()
    match = re.search(r'(\d+(?:\.\d+){1,3})', output)
    if not match:
        raise RuntimeError(f'could not parse Chrome version from: {output}')
    return match.group(1)


def safe_extract_extension(source: Path, target: Path) -> None:
    with zipfile.ZipFile(source, 'r') as archive:
        for info in archive.infolist():
            name = info.filename.replace('\\', '/')
            parts = Path(name).parts
            if not name or name.startswith('/') or '..' in parts:
                raise RuntimeError(f'unsafe Extension ZIP entry: {info.filename}')
        archive.extractall(target)
    if not (target / 'manifest.json').is_file():
        raise RuntimeError('exact Extension ZIP has no root manifest.json after extraction')


def confirm(prompt: str) -> None:
    answer = input(f'{prompt} Type YES to attest this check: ').strip()
    if answer != 'YES':
        raise RuntimeError('browser smoke aborted; no evidence was written')


def main() -> int:
    parser = argparse.ArgumentParser(description='Interactive clean-profile smoke for the exact controlled Extension ZIP in a real Chrome binary.')
    parser.add_argument('--controlled-manifest', type=Path, required=True)
    parser.add_argument('--orchestration-session', type=Path, required=True, help='native-smoke-complete checkpoint for this exact release')
    parser.add_argument('--chrome', type=Path, required=True)
    parser.add_argument('--expected-major', type=int, required=True)
    parser.add_argument('--engine-target', choices=('linux-x86_64', 'macos-arm64', 'windows-x86_64'), required=True)
    parser.add_argument('--fixture-url', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not sys.stdin.isatty():
        raise SystemExit('real browser acceptance is intentionally interactive; run this on a clean GUI machine with a TTY')
    fixture_url = urlparse(args.fixture_url)
    if fixture_url.scheme != 'http' or fixture_url.hostname not in {'127.0.0.1', 'localhost'}:
        raise SystemExit('release browser smoke fixture must be served from local HTTP (127.0.0.1/localhost)')

    manifest_path = args.controlled_manifest.resolve()
    manifest, manifest_sha = validate_controlled_manifest(manifest_path)
    orchestration = read_session(args.orchestration_session.resolve(), 'native-smoke-complete')
    require_release_identity(orchestration, manifest, manifest_sha)
    extension = manifest.get('extension')
    if not isinstance(extension, dict):
        raise SystemExit('controlled manifest has no Extension artifact')
    archive = manifest_path.parent / str(extension.get('artifact'))
    expected_sha = require_hex64(extension.get('sha256'), 'controlled Extension sha256')
    if not archive.is_file() or sha256_file(archive) != expected_sha:
        raise SystemExit('exact controlled Extension ZIP is missing or hash-mismatched')
    engine_entry = next((item for item in manifest.get('engines', []) if isinstance(item, dict) and item.get('target') == args.engine_target), None)
    if not isinstance(engine_entry, dict):
        raise SystemExit(f'controlled manifest has no Engine artifact for {args.engine_target}')
    engine_archive = manifest_path.parent / str(engine_entry.get('artifact'))
    engine_sha = require_hex64(engine_entry.get('sha256'), 'controlled Engine sha256')
    if not engine_archive.is_file() or sha256_file(engine_archive) != engine_sha:
        raise SystemExit('exact controlled Engine artifact for browser smoke is missing or hash-mismatched')

    chrome = args.chrome.resolve()
    if not chrome.is_file():
        raise SystemExit('Chrome executable does not exist')
    version = chrome_version(chrome)
    major = int(version.split('.', 1)[0])
    if major != args.expected_major:
        raise SystemExit(f'Chrome major mismatch: expected {args.expected_major}, got {version}')
    if args.expected_major < 148:
        raise SystemExit('release browser smoke refuses Chrome older than baseline 148')

    with tempfile.TemporaryDirectory(prefix=f'mte-chrome-{major}-') as temp_raw:
        temp = Path(temp_raw)
        extension_dir = temp / 'extension'
        profile_dir = temp / 'chrome-profile'
        extension_dir.mkdir()
        safe_extract_extension(archive, extension_dir)
        command = [
            str(chrome),
            f'--user-data-dir={profile_dir}',
            f'--load-extension={extension_dir}',
            f'--disable-extensions-except={extension_dir}',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-sync',
            args.fixture_url,
        ]
        proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            time.sleep(2)
            if proc.poll() is not None:
                raise RuntimeError('Chrome exited before browser smoke began')
            print(f'Controlled manifest: sha256:{manifest_sha}')
            print(f'Exact Extension ZIP: {archive.name} sha256:{expected_sha}')
            print(f'Chrome: {version}; clean temporary profile: {profile_dir}')
            print(f'Exact Local Engine to use: {args.engine_target} / {engine_archive.name} / sha256:{engine_sha}')
            print('Complete the release acceptance against this launched profile. Configure exactly the controlled Local Engine artifact printed above; do not rebuild/re-zip either artifact.')
            confirm('INSTALL — confirm the exact Extension loaded successfully and its manifest version/permissions are the expected candidate.')
            confirm('ACTIVATE — confirm first-run privacy consent and explicit page activation reach Ready on the authorized fixture.')
            confirm('TRANSLATE — confirm the authorized fixture translated successfully with the release Engine path and SFX remained preserved.')
            confirm('RESTORE — confirm Originals/restore returns the fixture to its original raster without reprocessing.')
            observation = {
                'schemaVersion': 2,
                'id': f'browser-chrome-{major}-{manifest_sha[:16]}',
                'artifactManifestSha256': manifest_sha,
                'orchestrationSessionSha256': orchestration['sessionSha256'],
                'sourceHeadSha': manifest['sourceHeadSha'],
                'kind': 'unpacked-extension',
                'platform': 'browser',
                'artifact': archive.name,
                'artifactSha256': expected_sha,
                'engineTargetAtTest': args.engine_target,
                'engineArtifactAtTest': engine_archive.name,
                'engineArtifactSha256AtTest': engine_sha,
                'browserVersion': version,
                'testedAtUtc': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                'cleanEnvironment': True,
                'checks': {'install': True, 'activate': True, 'translateFixture': True, 'restore': True},
                'fixtureUrl': args.fixture_url,
                'evidenceMode': 'interactive-human-observed-exact-bytes',
                'notes': 'The tool itself verified Chrome version, a fresh temporary browser profile, controlled-manifest binding, and exact Extension ZIP bytes. The four UX checks are explicit human attestations performed while that launched process is running.',
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
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
