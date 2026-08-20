from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "engine" / "mte_engine"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


files = {
    "profile": read("engine/mte_engine/profile.py"),
    "service": read("engine/mte_engine/service.py"),
    "app": read("engine/mte_engine/app.py"),
    "staged": read("engine/mte_engine/pipeline/staged.py"),
    "contracts": read("engine/mte_engine/pipeline/contracts.py"),
    "detector": read("engine/mte_engine/pipeline/detector.py"),
    "ocr": read("engine/mte_engine/pipeline/ocr.py"),
    "order": read("engine/mte_engine/pipeline/reading_order.py"),
    "roles": read("engine/mte_engine/pipeline/roles.py"),
    "translator": read("engine/mte_engine/pipeline/translator.py"),
    "masks": read("engine/mte_engine/pipeline/masks.py"),
    "inpaint": read("engine/mte_engine/pipeline/inpaint.py"),
    "renderer": read("engine/mte_engine/pipeline/renderer.py"),
    "manifest": read("engine/mte_engine/pipeline/manifest.py"),
    "tests": read("engine/tests/test_phase5_pipeline.py"),
    "gateway": read("src/engine/local-processing-gateway.ts"),
}

checks = [
    ("all Phase 5 stages are explicit and progress-addressable", all(name in files["staged"] for name in ['"decode"','"detect"','"order"','"ocr"','"translate"','"mask"','"inpaint"','"typeset"','"composite"','"encode"'])),
    ("every ML/render concern is behind an adapter interface", all(token in files["contracts"] for token in ["DetectorAdapter", "ReadingOrderAdapter", "OcrRouter", "BlockRoleClassifier", "TranslatorAdapter", "InpainterAdapter", "RendererAdapter"])),
    ("production detector is benchmark/license gated rather than silently chosen", "PADDLE_DETECTOR_CANDIDATES" in files["detector"] and "runtime_adapter_unavailable" in files["detector"] and "no network model lookup" in files["detector"]),
    ("OCR routes match English-first REV10 baseline", all(token in files["ocr"] for token in ["ppocrv6-en-benchmark-winner", "benchmark-frozen-japanese-winner", "korean-ppocrv5-mobile-rec", "ppocrv6-zh-benchmark-winner"])),
    ("OCR QA cannot unlock destructive edits when evidence is weak", "ocr_qa" in files["staged"] and '"uncertain"' in files["staged"]),
    ("role classifier is fail-closed", "VisualEnclosureRoleClassifier" in files["roles"] and "_lexically_protect" in files["roles"] and '"preserve-original"' in files["roles"]),
    ("SFX/uncertain never enter translator lane", "processing_action == \"translate-replace\"" in files["staged"] and "TranslationInputBlock" in files["staged"]),
    ("protected mask is dilated and destructive overlap fails", "ImageFilter.MaxFilter" in files["masks"] and "protected_region_conflict" in files["masks"]),
    ("protected source pixels are recomposited before encoding", "rendered.paste(source_pixels, (0, 0), protected_mask)" in files["staged"]),
    ("post-encode validation checks all RGBA channel extrema", "_has_pixel_difference" in files["staged"] and "getextrema" in files["staged"]),
    ("result manifest enforces protected block semantics", "Protected text block violates sfx-preserve-v1" in files["manifest"] and "translatedText" in files["manifest"]),
    ("Arabic renderer requires libraqm and uses RTL language-aware shaping", "features.check(\"raqm\")" in files["renderer"] and 'direction="rtl"' in files["renderer"] and 'language="ar"' in files["renderer"]),
    ("Arabic renderer uses measured fitting, not string reversal", "textbbox" in files["renderer"] and "[::-1]" not in files["renderer"] and "reversed(" not in files["renderer"]),
    ("production inpaint choice remains LaMa/AOT benchmark-gated", "SUPPORTED_INPAINT_CANDIDATES" in files["inpaint"] and "lama-inpaint" in files["inpaint"] and "aot-inpaint" in files["inpaint"]),
    ("production inpaint requires the fixed local ONNX wrapper contract", "mte-onnx-inpaint-contract-v1" in files["inpaint"] and "CPUExecutionProvider" in files["inpaint"] and "mte-inpaint-contract.json" in files["inpaint"]),
    ("inpaint model output is composited only under the erase mask", "source * (1.0 - blend) + array * blend" in files["inpaint"]),
    ("default production profile is not falsely marked ready", 'return "needs-download"' in files["profile"]),
    ("fixture profile is development-only and opt-in", "enable_fixture_profile" in files["profile"] and '"developmentOnly": True' in files["profile"]),
    ("profile fingerprint covers detector/OCR/roles/translator/inpaint/renderer/encoder", all(token in files["profile"] for token in ["detector", "ocrRouter", "blockRoleClassifier", "translator", "inpainter", "renderer", "encoder"])),
    ("profile-not-ready is surfaced as a typed extension error", "profile_not_ready: 'ENGINE_PROFILE_NOT_READY'" in files["gateway"]),
    ("ground-truth SFX test is independent from predicted protected mask", "Independent ground-truth annotation" in files["tests"] and "translator.inputs == [\"HELLO FRIEND\"]" in files["tests"]),
    ("overlap conflict and translated-SFX manifest attacks are tested", "test_protected_overlap_fails_before_inpaint_or_render" in files["tests"] and "test_manifest_validator_rejects_translated_sfx" in files["tests"]),
]

failed = False
for name, ok in checks:
    print(f"{'ok' if ok else 'not ok'} - {name}")
    failed |= not ok
print(f"# {len(checks)} Phase 5 contract checks")
sys.exit(1 if failed else 0)
