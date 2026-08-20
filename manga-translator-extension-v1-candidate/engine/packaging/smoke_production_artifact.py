from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'engine'))
from release_evidence import require_hex64, sha256_file, validate_controlled_manifest  # noqa: E402
from mte_engine.benchmark.freeze import load_freeze  # noqa: E402
from mte_engine.benchmark.source_binding import verify_current_source_binding  # noqa: E402

ORIGIN = 'chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
BASE = 'http://127.0.0.1:17891'


def http_json(method: str, path: str, *, token: str | None = None, body: dict | None = None, raw: bytes | None = None, content_type: str | None = None, extra_headers: dict[str, str] | None = None, timeout: float = 20) -> tuple[int, dict | bytes, dict[str, str]]:
    headers = {'Origin': ORIGIN}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    if body is not None:
        raw = json.dumps(body, separators=(',', ':')).encode('utf-8')
        content_type = 'application/json'
    if raw is not None and content_type:
        headers['Content-Type'] = content_type
    if extra_headers:
        headers.update(extra_headers)
    request = urllib.request.Request(BASE + path, data=raw, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
            response_headers = {k.lower(): v for k, v in response.headers.items()}
            if response_headers.get('content-type', '').split(';', 1)[0] == 'application/json' and data:
                return response.status, json.loads(data), response_headers
            return response.status, data, response_headers
    except urllib.error.HTTPError as exc:
        data = exc.read()
        try:
            payload: dict | bytes = json.loads(data) if data else b''
        except json.JSONDecodeError:
            payload = data
        return exc.code, payload, {k.lower(): v for k, v in exc.headers.items()}


def wait_health(timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status, _, _ = http_json('GET', '/healthz', timeout=1)
            if status == 204:
                return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.25)
    raise RuntimeError('exact Engine artifact did not become healthy')


def extract_portable_artifact(artifact: Path, target: Path) -> None:
    lower = artifact.name.lower()
    if lower.endswith('.zip'):
        with zipfile.ZipFile(artifact, 'r') as archive:
            for info in archive.infolist():
                name = info.filename.replace('\\', '/')
                parts = Path(name).parts
                mode = (info.external_attr >> 16) & 0o170000
                if not name or name.startswith('/') or '..' in parts:
                    raise RuntimeError(f'unsafe ZIP entry: {info.filename}')
                if mode == 0o120000:
                    raise RuntimeError(f'portable Engine ZIP symlink is forbidden: {info.filename}')
            archive.extractall(target)
        return
    if lower.endswith(('.tar.gz', '.tgz', '.tar')):
        with tarfile.open(artifact, 'r:*') as archive:
            archive.extractall(target, filter='data')
        return
    raise RuntimeError(f'unsupported portable Engine release artifact format for smoke: {artifact.name}')


def find_executable(root: Path) -> Path:
    name = 'mte-engine.exe' if os.name == 'nt' else 'mte-engine'
    matches = [p for p in root.rglob(name) if p.is_file()]
    if not matches:
        raise RuntimeError(f'could not locate {name} in exact Engine artifact')
    matches.sort(key=lambda p: (len(p.parts), str(p)))
    return matches[0]


def install_exact_artifact(artifact: Path, temp: Path) -> tuple[Path, str, Callable[[], None]]:
    lower = artifact.name.lower()
    if lower.endswith('.pkg'):
        if sys.platform != 'darwin':
            raise RuntimeError('macOS .pkg controlled artifact can only be smoked on macOS')
        install_root = Path('/Applications/Manga Translator Engine')
        if install_root.exists():
            raise RuntimeError('clean-machine .pkg smoke refused because Manga Translator Engine is already installed')
        subprocess.run(['pkgutil', '--check-signature', str(artifact)], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['xcrun', 'stapler', 'validate', str(artifact)], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['spctl', '-a', '-vv', '-t', 'install', str(artifact)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['sudo', '-n', 'installer', '-pkg', str(artifact), '-target', '/'], check=True, stdout=subprocess.DEVNULL)
        executable = install_root / 'mte-engine'
        if not executable.is_file():
            subprocess.run(['sudo', '-n', 'rm', '-rf', str(install_root)], check=False)
            subprocess.run(['sudo', '-n', 'pkgutil', '--forget', 'org.mte.local-engine'], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            raise RuntimeError('installed .pkg did not place mte-engine at its declared install location')

        def cleanup() -> None:
            subprocess.run(['sudo', '-n', 'rm', '-rf', str(install_root)], check=True)
            subprocess.run(['sudo', '-n', 'pkgutil', '--forget', 'org.mte.local-engine'], check=True, stdout=subprocess.DEVNULL)
            if install_root.exists():
                raise RuntimeError('macOS .pkg smoke cleanup failed to remove the installed Engine')

        return executable, 'macos-pkg-system-install', cleanup

    extracted = temp / 'artifact'
    extracted.mkdir()
    extract_portable_artifact(artifact, extracted)
    executable = find_executable(extracted)

    def cleanup() -> None:
        shutil.rmtree(extracted)
        if extracted.exists():
            raise RuntimeError('portable Engine smoke cleanup failed')

    return executable, 'portable-clean-extract', cleanup

def verify_models(freeze: dict, model_root: Path) -> Path:
    pins = freeze.get('selectedArtifacts')
    if not isinstance(pins, list) or not pins:
        raise RuntimeError('controlled production freeze has no selected artifact pins')
    by_id: dict[str, dict] = {}
    for pin in pins:
        if not isinstance(pin, dict) or not isinstance(pin.get('artifactId'), str) or not isinstance(pin.get('expectedFilename'), str):
            raise RuntimeError('production freeze selected artifact pin is malformed')
        expected = require_hex64(pin.get('sha256'), f'{pin["artifactId"]} sha256')
        path = (model_root / pin['expectedFilename']).resolve()
        try:
            path.relative_to(model_root.resolve())
        except ValueError as exc:
            raise RuntimeError(f'unsafe model artifact path in freeze: {pin["artifactId"]}') from exc
        if not path.is_file():
            raise RuntimeError(f'qualified model artifact is missing on smoke runner: {pin["artifactId"]}')
        if sha256_file(path) != expected:
            raise RuntimeError(f'qualified model artifact hash mismatch on smoke runner: {pin["artifactId"]}')
        by_id[pin['artifactId']] = pin
    renderer = freeze.get('renderer')
    if not isinstance(renderer, dict) or not isinstance(renderer.get('fontArtifactId'), str):
        raise RuntimeError('production freeze renderer font artifact is missing')
    font_pin = by_id.get(renderer['fontArtifactId'])
    if not font_pin:
        raise RuntimeError('production freeze font artifact is not selected')
    return (model_root / font_pin['expectedFilename']).resolve()


def processing_spec() -> dict[str, object]:
    return {
        'schemaVersion': 1,
        'sourceLanguage': 'en',
        'targetLanguage': 'ar',
        'textRolePolicy': {
            'translatableKinds': ['dialogue', 'narration'],
            'sfxAction': 'preserve-original',
            'uncertainAction': 'preserve-original',
            'revision': 'sfx-preserve-v1',
        },
        'output': {'kind': 'translated-raster-image', 'preserveDimensions': True},
        'profileId': 'default-v1',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Smoke the exact archived production Engine bytes against frozen qualified artifacts.')
    parser.add_argument('--controlled-manifest', type=Path, required=True)
    parser.add_argument('--target', choices=('linux-x86_64', 'macos-arm64', 'windows-x86_64'), required=True)
    parser.add_argument('--model-artifacts-dir', type=Path, required=True)
    parser.add_argument('--fixture', type=Path, default=ROOT / 'tests' / 'fixtures' / 'assets' / 'page-1.png')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()

    manifest_path = args.controlled_manifest.resolve()
    manifest, manifest_sha = validate_controlled_manifest(manifest_path)
    if manifest.get('releaseClass') not in {'private-v1', 'public-v1'}:
        raise SystemExit('production Engine smoke requires a V1 controlled manifest')
    entry = next((item for item in manifest.get('engines', []) if isinstance(item, dict) and item.get('target') == args.target), None)
    if not isinstance(entry, dict):
        raise SystemExit(f'controlled manifest has no Engine artifact for {args.target}')
    artifact = manifest_path.parent / str(entry['artifact'])
    expected_artifact_sha = require_hex64(entry.get('sha256'), 'controlled Engine sha256')
    if not artifact.is_file() or sha256_file(artifact) != expected_artifact_sha:
        raise SystemExit('exact controlled Engine artifact is missing or hash-mismatched')

    freeze_path = manifest_path.parent / 'production-profile-freeze.json'
    freeze_meta = next((item for item in manifest.get('metadata', []) if isinstance(item, dict) and item.get('artifact') == 'production-profile-freeze.json'), None)
    if not isinstance(freeze_meta, dict):
        raise SystemExit('controlled manifest does not bind production-profile-freeze.json metadata')
    expected_freeze_file_sha = require_hex64(freeze_meta.get('sha256'), 'controlled production freeze file sha256')
    if not freeze_path.is_file() or sha256_file(freeze_path) != expected_freeze_file_sha:
        raise SystemExit('controlled production freeze bytes differ from controlled manifest metadata')
    freeze = load_freeze(freeze_path)
    if freeze is None:
        raise SystemExit('controlled production freeze is missing or fails its canonical self-hash/schema validation')
    qualified = freeze.get('qualifiedSource')
    if not isinstance(qualified, dict) or qualified.get('sourceHeadSha') != manifest.get('sourceHeadSha'):
        raise SystemExit('controlled production freeze source commit differs from controlled manifest')
    try:
        verify_current_source_binding(ROOT, qualified)
    except ValueError as exc:
        raise SystemExit(f'controlled production freeze runtime source binding differs from this checkout: {exc}') from exc
    model_root = args.model_artifacts_dir.resolve()
    if not model_root.is_dir():
        raise SystemExit('qualified model artifact directory is unavailable on this protected runner')
    font_path = verify_models(freeze, model_root)
    fixture = args.fixture.resolve()
    if not fixture.is_file():
        raise SystemExit('authorized smoke fixture is missing')
    fixture_bytes = fixture.read_bytes()
    fixture_sha = hashlib.sha256(fixture_bytes).hexdigest()

    with tempfile.TemporaryDirectory(prefix=f'mte-exact-{args.target}-') as temp_raw:
        temp = Path(temp_raw)
        executable, installation_mode, cleanup_installation = install_exact_artifact(artifact, temp)
        cleanup_verified = False
        try:
            data_dir = temp / 'engine-data'
            env = os.environ.copy()
            env.update({
                'MTE_ENGINE_DATA_DIR': str(data_dir),
                'MTE_MODEL_ARTIFACTS_DIR': str(model_root),
                'MTE_ARABIC_FONT_PATH': str(font_path),
                'MTE_ENABLE_EXTERNAL_TEXT_TRANSLATION': '1',
            })
            if not env.get('MTE_OPENAI_API_KEY'):
                raise SystemExit('MTE_OPENAI_API_KEY is required for the frozen production translation smoke')
            version = subprocess.check_output([str(executable), 'version'], env=env, text=True, timeout=20).strip()
            if not version.startswith('mte-engine '):
                raise SystemExit(f'exact artifact version command failed: {version}')
            token = subprocess.check_output([str(executable), 'show-token'], env=env, text=True, timeout=20).strip()
            if len(token) < 20:
                raise SystemExit('exact artifact did not emit a valid pairing token')
            proc = subprocess.Popen([str(executable), 'run'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ticket: str | None = None
            try:
                wait_health()
                status, caps, _ = http_json('GET', '/v1/capabilities', token=token)
                if status != 200 or not isinstance(caps, dict):
                    raise RuntimeError(f'capabilities failed with status {status}')
                profile = next((p for p in caps.get('profiles', []) if isinstance(p, dict) and p.get('profileId') == 'default-v1'), None)
                if not isinstance(profile, dict) or profile.get('state') != 'ready':
                    state = profile.get('state') if isinstance(profile, dict) else 'missing'
                    raise RuntimeError(f'default-v1 is not ready in exact artifact smoke: {state}')
                fingerprint = str(profile.get('profileFingerprint'))
                require_hex64(fingerprint, 'production profileFingerprint')
                privacy = profile.get('privacy')
                if not isinstance(privacy, dict) or any(type(privacy.get(key)) is not bool for key in ('imageLeavesDevice', 'ocrTextLeavesDevice', 'visualContextLeavesDevice')):
                    raise RuntimeError('default-v1 privacy descriptor is not fully frozen')
                providers = profile.get('externalProviders')
                if not isinstance(providers, list):
                    raise RuntimeError('default-v1 external provider list is invalid')
                remote = any(privacy.values())
                consent = None
                if remote:
                    if not providers:
                        raise RuntimeError('remote production profile does not name a provider')
                    consent = {
                        'schemaVersion': 1,
                        'disclosureVersion': '2026-08-19.remote-transfer.v1',
                        'profileId': 'default-v1',
                        'profileFingerprint': fingerprint,
                        'privacyDescriptor': privacy,
                        'externalProviderNames': providers,
                        'acceptedAt': int(time.time() * 1000),
                    }
                body = {
                    'jobId': f'release-smoke-{args.target}',
                    'idempotencyKey': 'sha256:' + hashlib.sha256((manifest_sha + args.target + fixture_sha).encode()).hexdigest(),
                    'sourceSha256': 'sha256:' + fixture_sha,
                    'sourceBytes': len(fixture_bytes),
                    'sourceMime': 'image/png',
                    'processingSpec': processing_spec(),
                    'expectedProfileFingerprint': fingerprint,
                    'remoteTransferConsent': consent,
                }
                status, created, _ = http_json('POST', '/v1/jobs', token=token, body=body)
                if status != 200 or not isinstance(created, dict) or not isinstance(created.get('engineTicket'), str):
                    raise RuntimeError(f'create production smoke job failed with status {status}')
                ticket = created['engineTicket']
                status, _, _ = http_json('PUT', f'/v1/jobs/{ticket}/source', token=token, raw=fixture_bytes, content_type='image/png', extra_headers={'X-Source-SHA256': 'sha256:' + fixture_sha}, timeout=60)
                if status != 200:
                    raise RuntimeError(f'upload production smoke source failed with status {status}')
                status, _, _ = http_json('POST', f'/v1/jobs/{ticket}/start', token=token, body={'remoteTransferConsent': consent}, timeout=30)
                if status != 200:
                    raise RuntimeError(f'start production smoke job failed with status {status}')
                deadline = time.monotonic() + 300
                final: dict | None = None
                while time.monotonic() < deadline:
                    status, payload, _ = http_json('GET', f'/v1/jobs/{ticket}', token=token, timeout=10)
                    if status != 200 or not isinstance(payload, dict):
                        raise RuntimeError(f'poll production smoke job failed with status {status}')
                    if payload.get('state') in {'succeeded', 'failed', 'cancelled', 'interrupted'}:
                        final = payload
                        break
                    time.sleep(0.5)
                if not final or final.get('state') != 'succeeded':
                    code = ((final or {}).get('error') or {}).get('code') if isinstance((final or {}).get('error'), dict) else None
                    raise RuntimeError(f'production translation smoke did not succeed; terminal={final.get("state") if final else "timeout"}; code={code or "none"}')
                status, result_bytes, result_headers = http_json('GET', f'/v1/jobs/{ticket}/result', token=token, timeout=60)
                if status != 200 or not isinstance(result_bytes, bytes) or not result_bytes:
                    raise RuntimeError('production smoke result could not be downloaded')
                result_sha = hashlib.sha256(result_bytes).hexdigest()
                if result_headers.get('x-result-sha256') != 'sha256:' + result_sha:
                    raise RuntimeError('production smoke result hash header does not match result bytes')
                status, result_manifest, _ = http_json('GET', f'/v1/jobs/{ticket}/result-manifest', token=token)
                if status != 200 or not isinstance(result_manifest, dict) or result_manifest.get('profileFingerprint') != fingerprint:
                    raise RuntimeError('production smoke result manifest is not bound to the tested profile fingerprint')
                status, _, _ = http_json('DELETE', f'/v1/jobs/{ticket}', token=token)
                if status != 204:
                    raise RuntimeError('production smoke cleanup/restore failed')
                ticket = None
                observation = {
                    'schemaVersion': 2,
                    'id': f'engine-{args.target}-{manifest_sha[:16]}',
                    'artifactManifestSha256': manifest_sha,
                    'sourceHeadSha': manifest['sourceHeadSha'],
                    'kind': 'engine-artifact',
                    'platform': args.target,
                    'artifact': artifact.name,
                    'artifactSha256': expected_artifact_sha,
                    'testedAtUtc': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                    'cleanEnvironment': True,
                    'checks': {'install': True, 'activate': True, 'translateFixture': True, 'restore': True},
                    'profileId': 'default-v1',
                    'profileStateAtTest': 'ready',
                    'profileFingerprint': fingerprint,
                    'privacyDescriptor': privacy,
                    'externalProviderNames': providers,
                    'fixtureSha256': fixture_sha,
                    'resultSha256': result_sha,
                    'engineVersion': caps.get('engineVersion'),
                    'notes': 'Automated exact-archive production smoke; model bytes are re-hashed against the controlled production freeze before launch.',
                }
                observation['installationMode'] = installation_mode
                observation['cleanInstallVerified'] = True
            finally:
                if ticket:
                    try:
                        http_json('DELETE', f'/v1/jobs/{ticket}', token=token, timeout=2)
                    except Exception:
                        pass
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
        finally:
            cleanup_installation()
            cleanup_verified = True
        if not cleanup_verified:
            raise RuntimeError('exact Engine smoke cleanup was not verified')
        observation['installationCleanupVerified'] = True
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(observation, indent=2) + '\n', encoding='utf-8')
        print(args.output)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError, zipfile.BadZipFile, tarfile.TarError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
