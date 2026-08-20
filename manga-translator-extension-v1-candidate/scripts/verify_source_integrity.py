from __future__ import annotations

import argparse
from pathlib import Path

from source_integrity import verify_source_integrity


def main() -> int:
    parser = argparse.ArgumentParser(description='Verify SOURCE_SHA256SUMS coverage and digests for every committed source file.')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    errors = verify_source_integrity(root)
    if errors:
        print(f'Source integrity blocked ({len(errors)}):')
        for error in errors:
            print(f'- {error}')
        return 2
    print(f'Source integrity verified: {len((root / "SOURCE_SHA256SUMS.txt").read_text(encoding="utf-8").splitlines())} files')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
