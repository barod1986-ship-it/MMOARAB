from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / 'engine'
VERSIONS = json.loads((ENGINE / 'packaging' / 'runtime-versions.json').read_text(encoding='utf-8'))


def command_version(command: list[str]) -> str:
    return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()


def require_release_environment() -> None:
    if not (ENGINE / 'uv.lock').is_file():
        raise SystemExit('release build refused: engine/uv.lock is missing')
    expected_python = str(VERSIONS['python'])
    actual_python = platform.python_version()
    if actual_python != expected_python:
        raise SystemExit(f'release build refused: Python {expected_python} required, got {actual_python}')
    uv = command_version(['uv', '--version']).split()[-1]
    if uv != VERSIONS['uv']:
        raise SystemExit(f'release build refused: uv {VERSIONS["uv"]} required, got {uv}')
    pyinstaller = command_version([sys.executable, '-m', 'PyInstaller', '--version'])
    if pyinstaller != VERSIONS['pyinstaller']:
        raise SystemExit(f'release build refused: PyInstaller {VERSIONS["pyinstaller"]} required, got {pyinstaller}')
    subprocess.run(['uv', 'lock', '--check'], cwd=ENGINE, check=True)


def target_id() -> str:
    os_name = {'Windows': 'windows', 'Darwin': 'macos', 'Linux': 'linux'}.get(platform.system())
    machine = platform.machine().lower()
    arch = {'amd64': 'x86_64', 'x86_64': 'x86_64', 'arm64': 'arm64', 'aarch64': 'arm64'}.get(machine, machine)
    if not os_name:
        raise SystemExit(f'unsupported packaging host: {platform.system()}')
    return f'{os_name}-{arch}'


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def archive_dist(dist_dir: Path, output_dir: Path, target: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f'mte-local-engine-{VERSIONS["engineVersion"]}-{target}'
    if target.startswith('windows-'):
        archive = output_dir / f'{stem}.zip'
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for path in sorted(dist_dir.rglob('*')):
                if path.is_file():
                    zf.write(path, Path('mte-engine') / path.relative_to(dist_dir))
    else:
        archive = output_dir / f'{stem}.tar.gz'
        with tarfile.open(archive, 'w:gz', format=tarfile.PAX_FORMAT) as tf:
            tf.add(dist_dir, arcname='mte-engine', recursive=True)
    return archive


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--release', action='store_true', help='Require exact locked release environment.')
    parser.add_argument('--output', type=Path, default=ROOT / 'release' / 'candidates')
    args = parser.parse_args()
    if args.release:
        require_release_environment()
    target = target_id()
    work = ENGINE / '.packaging-build'
    dist = ENGINE / '.packaging-dist'
    shutil.rmtree(work, ignore_errors=True)
    shutil.rmtree(dist, ignore_errors=True)
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
        '--workpath', str(work), '--distpath', str(dist),
        str(ENGINE / 'packaging' / 'common' / 'mte-engine.spec'),
    ], cwd=ENGINE, check=True)
    built = dist / 'mte-engine'
    executable = built / ('mte-engine.exe' if platform.system() == 'Windows' else 'mte-engine')
    if not executable.is_file():
        raise SystemExit(f'PyInstaller output missing executable: {executable}')
    version_output = command_version([str(executable), 'version'])
    if f'mte-engine {VERSIONS["engineVersion"]}' not in version_output:
        raise SystemExit(f'packaged engine reported unexpected version: {version_output}')
    archive = archive_dist(built, args.output, target)
    compatibility = {
        'schemaVersion': 1,
        'target': target,
        'engineVersion': VERSIONS['engineVersion'],
        'protocolMajor': VERSIONS['protocolMajor'],
        'pythonBuildRuntime': platform.python_version(),
        'packagingTool': f'PyInstaller {command_version([sys.executable, "-m", "PyInstaller", "--version"])}',
        'artifact': archive.name,
        'sha256': 'sha256:' + hash_file(archive),
        'signed': False,
        'notarized': False,
    }
    meta = args.output / f'{archive.name}.compatibility.json'
    meta.write_text(json.dumps(compatibility, indent=2) + '\n', encoding='utf-8')
    sums = args.output / 'SHA256SUMS'
    existing = [line for line in sums.read_text(encoding='utf-8').splitlines() if line and not line.endswith(f'  {archive.name}') and not line.endswith(f'  {meta.name}')] if sums.exists() else []
    existing += [f'{hash_file(archive)}  {archive.name}', f'{hash_file(meta)}  {meta.name}']
    sums.write_text('\n'.join(existing) + '\n', encoding='utf-8')
    print(archive)


if __name__ == '__main__':
    main()
