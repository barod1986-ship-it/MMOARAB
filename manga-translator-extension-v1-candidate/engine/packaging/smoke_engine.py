from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('executable', type=Path)
    args = parser.parse_args()
    executable = args.executable.resolve()
    if not executable.is_file():
        raise SystemExit('engine executable not found')
    version = subprocess.check_output([str(executable), 'version'], text=True, timeout=10).strip()
    if not version.startswith('mte-engine '):
        raise SystemExit(f'unexpected version output: {version}')
    with tempfile.TemporaryDirectory(prefix='mte-clean-smoke-') as temp:
        env = os.environ.copy()
        env['MTE_ENGINE_DATA_DIR'] = temp
        proc = subprocess.Popen([str(executable), 'run'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                try:
                    req = urllib.request.Request('http://127.0.0.1:17891/healthz', method='GET')
                    with urllib.request.urlopen(req, timeout=1) as response:
                        if response.status == 204:
                            print(f'ok: {version}; healthz=204')
                            return
                except (urllib.error.URLError, OSError):
                    time.sleep(0.25)
            raise SystemExit('engine did not become healthy on fixed loopback port')
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


if __name__ == '__main__':
    main()
