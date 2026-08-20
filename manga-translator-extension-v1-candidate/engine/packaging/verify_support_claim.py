from __future__ import annotations

import argparse
import json
from pathlib import Path

CLAIMS = Path(__file__).with_name('support-claims.json')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('target')
    parser.add_argument('--require-public', action='store_true')
    args = parser.parse_args()
    value = json.loads(CLAIMS.read_text(encoding='utf-8'))
    target = next((item for item in value['targets'] if item['id'] == args.target), None)
    if target is None:
        raise SystemExit(f'unsupported target: {args.target}')
    if args.require_public and target.get('publicSupportClaimed') is not True:
        raise SystemExit(f'public release refused: {args.target} is not yet an audited public support claim')
    print(json.dumps(target, indent=2))


if __name__ == '__main__':
    main()
