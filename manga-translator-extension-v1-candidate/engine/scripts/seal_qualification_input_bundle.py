from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.qualification_bundle import QualificationBundleError, resolve_below, seal_qualification_input_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and seal the exact operator-controlled inputs for one real production qualification prepare run.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--corpus", required=True, help="Corpus manifest path relative to --root.")
    parser.add_argument("--reviews-dir", required=True, help="Canonical artifact review directory relative to --root.")
    parser.add_argument("--manual-artifacts-dir", required=True, help="Reviewed LaMa/AOT package directory relative to --root.")
    parser.add_argument("--output", required=True, help="Bundle path relative to --root.")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    if args.root.is_symlink():
        raise SystemExit("qualification input root must be a real directory, not a symlink")
    root = args.root.resolve(strict=True)
    output = resolve_below(root, args.output, label="bundle output", kind="file", may_not_exist=True)
    if output.exists() and not args.replace:
        raise SystemExit("qualification input bundle already exists; use --replace only after reviewing the new input bytes")
    bundle = seal_qualification_input_bundle(root, corpus_relative=args.corpus, reviews_relative=args.reviews_dir, manual_relative=args.manual_artifacts_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"qualificationInputBundle": str(output), "bundleSha256": bundle["bundleSha256"], "corpusId": bundle["corpus"]["corpusId"], "artifactReviewCount": len(bundle["artifactReviews"]), "manualArtifactCount": len(bundle["manualArtifacts"])}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except QualificationBundleError as exc:
        raise SystemExit(str(exc))
