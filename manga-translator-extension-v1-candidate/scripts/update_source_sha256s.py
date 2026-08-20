from __future__ import annotations

import argparse
from pathlib import Path

from source_integrity import MANIFEST, render_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description='Regenerate SOURCE_SHA256SUMS deterministically from the source tree.')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    target = root / MANIFEST
    target.write_text(render_manifest(root), encoding='utf-8', newline='\n')
    print(target)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
