from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / 'engine'
VERSIONS = json.loads((ENGINE / 'packaging' / 'runtime-versions.json').read_text(encoding='utf-8'))


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise SystemExit(f'release metadata refused: {name} is unavailable')
    return path


def validate_cyclonedx(path: Path) -> None:
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('bomFormat') != 'CycloneDX' or value.get('specVersion') != '1.5' or not isinstance(value.get('components'), list):
        raise SystemExit('release metadata refused: uv CycloneDX output failed schema sanity checks')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'release' / 'metadata')
    args = parser.parse_args()
    if not (ENGINE / 'uv.lock').is_file():
        raise SystemExit('release metadata refused: engine/uv.lock is missing')
    uv = require_tool('uv')
    uv_version = subprocess.check_output([uv, '--version'], text=True).strip().split()[-1]
    if uv_version != VERSIONS['uv']:
        raise SystemExit(f'release metadata refused: uv {VERSIONS["uv"]} required, got {uv_version}')
    subprocess.run([uv, 'lock', '--check'], cwd=ENGINE, check=True)
    args.output.mkdir(parents=True, exist_ok=True)
    engine_sbom = args.output / 'engine.cyclonedx-1.5.json'
    pylock = args.output / 'engine.pylock.toml'
    subprocess.run([uv, 'export', '--locked', '--format', 'cyclonedx1.5', '--output-file', str(engine_sbom)], cwd=ENGINE, check=True)
    subprocess.run([uv, 'export', '--locked', '--format', 'pylock.toml', '--output-file', str(pylock)], cwd=ENGINE, check=True)
    validate_cyclonedx(engine_sbom)
    distribution = json.loads((ENGINE / 'model-catalog' / 'model-distribution-v1.json').read_text(encoding='utf-8'))
    models = [{
        'artifactId': item['artifactId'],
        'revision': item['revision'],
        'licenseSpdx': item['licenseSpdx'],
        'redistribution': item['redistribution'],
        'sha256': item['sha256'],
    } for item in distribution.get('artifacts', [])]
    (args.output / 'MODEL_LICENSES.json').write_text(json.dumps({'schemaVersion': 1, 'catalogRevision': distribution.get('catalogRevision'), 'artifacts': models}, indent=2) + '\n', encoding='utf-8')
    print(args.output)


if __name__ == '__main__':
    main()
