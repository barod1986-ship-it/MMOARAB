from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.corpus import load_corpus, production_corpus_gate, validate_corpus


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the legal production benchmark corpus manifest and files.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--structure-only", action="store_true", help="Validate manifest structure without opening corpus files. Never sufficient for a release freeze.")
    args = parser.parse_args()
    manifest = load_corpus(args.manifest, verify_files=not args.structure_only)
    summary = validate_corpus(manifest, base_dir=args.manifest.parent, verify_files=not args.structure_only)
    passed, reasons = production_corpus_gate(summary)
    print(json.dumps({"productionCorpusGatePassed": passed, "reasons": reasons, "summary": summary}, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
