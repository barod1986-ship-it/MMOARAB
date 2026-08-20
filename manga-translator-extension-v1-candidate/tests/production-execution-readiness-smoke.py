from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / 'scripts' / 'probe_production_execution_environment.py'
CONTRACT = ROOT / 'release-control' / 'production-execution-contract.json'


def run(*args: str, env: dict[str, str] | None = None):
    return subprocess.run([sys.executable, str(PROBE), *args], cwd=ROOT, text=True, capture_output=True, env=env)


def main() -> int:
    result = run('--strict')
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report['passed'] is True and report['role'] == 'static'

    with tempfile.TemporaryDirectory(prefix='mte-readiness-') as td:
        model_root = Path(td) / 'models'; model_root.mkdir()
        env = dict(os.environ)
        env['MTE_OPENAI_API_KEY'] = 'do-not-print-this-secret'
        env['MTE_QUALIFIED_MODEL_ARTIFACTS_DIR'] = str(model_root)
        result = run('--role', 'release-smoke-linux-x86_64', env=env)
        assert 'do-not-print-this-secret' not in result.stdout + result.stderr
        live = json.loads(result.stdout)
        secret = next(x for x in live['checks'] if x['name'] == 'secret:MTE_OPENAI_API_KEY')
        assert secret['passed'] is True and secret['sensitive'] is True

        broken = Path(td) / 'contract.json'
        data = json.loads(CONTRACT.read_text(encoding='utf-8'))
        data['publicSigning']['windows']['action'] = 'Azure/artifact-signing-action@' + '0' * 40
        broken.write_text(json.dumps(data), encoding='utf-8')
        result = run('--contract', str(broken), '--strict')
        assert result.returncode != 0
        tampered = json.loads(result.stdout)
        failed = [x['name'] for x in tampered['checks'] if not x['passed']]
        assert 'windows-artifact-signing-action' in failed

    print('Production execution readiness tooling: 3/3 passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
