from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.common import require_dict, require_list, sha256_path
from mte_engine.benchmark.corpus_sources import load_source_registry, source_registry_digest
from mte_engine.benchmark.corpus import load_corpus, production_corpus_gate, validate_corpus


def _contained(root: Path, relative: str, *, label: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"{label} must stay inside the corpus root")
    root = root.resolve()
    cursor = root
    for part in candidate.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"{label} may not traverse symlinks")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} escapes the corpus root") from exc
    if not resolved.is_file():
        raise ValueError(f"{label} is missing")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description="Seal a reviewed corpus draft by computing image/annotation/clean-reference digests. Existing mismatched digests are refused.")
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--corpus-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        manifest = require_dict(json.loads(args.draft.read_text(encoding="utf-8")), label="corpus draft")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"Cannot read corpus draft: {exc}")
    registry = load_source_registry()
    manifest["schemaVersion"] = 2
    manifest["policyRevision"] = "rev10-production-corpus-v2"
    manifest["sourceRegistryRevision"] = registry["registryRevision"]
    manifest["sourceRegistrySha256"] = source_registry_digest(registry)
    pages = require_list(manifest.get("pages"), label="pages")
    for index, raw in enumerate(pages):
        page = require_dict(raw, label=f"pages[{index}]")
        rights = require_dict(page.get("rights"), label=f"pages[{index}].rights")
        review_rel = rights.get("reviewRecordPath")
        if not isinstance(review_rel, str) or not review_rel:
            raise SystemExit(f"pages[{index}].rights.reviewRecordPath is required")
        review_path = _contained(args.corpus_root, review_rel, label=f"pages[{index}].rights.reviewRecordPath")
        review_digest = sha256_path(review_path)
        existing_review_digest = rights.get("reviewRecordSha256")
        if existing_review_digest is not None and existing_review_digest != review_digest:
            raise SystemExit(f"pages[{index}].rights.reviewRecordSha256 conflicts with actual review bytes")
        rights["reviewRecordSha256"] = review_digest
        for path_key, hash_key in (("imagePath", "imageSha256"), ("annotationPath", "annotationSha256"), ("cleanReferencePath", "cleanReferenceSha256")):
            relative = page.get(path_key)
            if relative is None and path_key == "cleanReferencePath":
                continue
            if not isinstance(relative, str) or not relative:
                raise SystemExit(f"pages[{index}].{path_key} is required")
            path = _contained(args.corpus_root, relative, label=f"pages[{index}].{path_key}")
            digest = sha256_path(path)
            existing = page.get(hash_key)
            if existing is not None and existing != digest:
                raise SystemExit(f"pages[{index}].{hash_key} conflicts with actual file bytes")
            page[hash_key] = digest
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(args.output.suffix + ".tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(args.output)
    sealed = load_corpus(args.output, verify_files=True)
    summary = validate_corpus(sealed, base_dir=args.output.parent, verify_files=True)
    passed, reasons = production_corpus_gate(summary)
    print(json.dumps({"sealed": True, "productionCorpusGatePassed": passed, "reasons": reasons, "summary": summary, "manifestSha256": sha256_path(args.output)}, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
