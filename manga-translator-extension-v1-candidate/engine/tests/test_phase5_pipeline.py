from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw

from mte_engine.errors import EngineApiError
from mte_engine.pipeline.contracts import DetectedRegion, StyleHints
from mte_engine.pipeline.detector import ReferenceDetector
from mte_engine.pipeline.inpaint import ReferenceSolidInpainter
from mte_engine.pipeline.manifest import validate_manifest
from mte_engine.pipeline.ocr import ReferenceOcrRouter, route_for_language
from mte_engine.pipeline.reading_order import HeuristicReadingOrder
from mte_engine.pipeline.renderer import ArabicRenderer
from mte_engine.pipeline.roles import ConservativeRoleClassifier
from mte_engine.pipeline.staged import StagedPipeline
from mte_engine.pipeline.translator import ReferenceTranslator


def arabic_font() -> Path:
    for candidate in [
        Path("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/opentype/freefont/FreeSans.ttf"),
    ]:
        if candidate.is_file():
            return candidate
    pytest.skip("Arabic-capable font unavailable")


def rect(x0: int, y0: int, x1: int, y1: int):
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def source_page(path: Path) -> Image.Image:
    image = Image.new("RGBA", (420, 320), "white")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((30, 30, 250, 125), radius=20, outline="black", width=3, fill=(248, 248, 248, 255))
    draw.rectangle((280, 175, 400, 280), fill=(210, 225, 245, 255), outline="black", width=2)
    # Dense distinctive pixels inside the ground-truth SFX area.
    for x in range(292, 388, 4):
        draw.line((x, 185, 400 - (x - 280), 270), fill=(20 + x % 200, 30, 170, 255), width=2)
    image.save(path, format="PNG")
    return image


class RecordingTranslator(ReferenceTranslator):
    def __init__(self):
        super().__init__({"HELLO FRIEND": "مرحبًا يا صديقي"})
        self.inputs: list[str] = []

    def translate_page(self, **kwargs):
        self.inputs = [block.source for block in kwargs["blocks"]]
        return super().translate_page(**kwargs)


def pipeline(regions, translator=None):
    return StagedPipeline(
        detector=ReferenceDetector(regions),
        reading_order=HeuristicReadingOrder(),
        ocr=ReferenceOcrRouter(),
        roles=ConservativeRoleClassifier(),
        translator=translator or ReferenceTranslator(),
        inpainter=ReferenceSolidInpainter(),
        renderer=ArabicRenderer(arabic_font(), max_size=46),
    )


def test_full_staged_reference_pipeline_preserves_ground_truth_sfx(tmp_path: Path):
    path = tmp_path / "page.png"
    before = source_page(path)
    dialogue = DetectedRegion("dialogue-1", rect(45, 45, 235, 110), 0.99, text_hint="HELLO FRIEND", kind_hint="dialogue")
    sfx = DetectedRegion("sfx-1", rect(285, 180, 398, 278), 0.99, text_hint="BOOM", kind_hint="sfx", style_hints=StyleHints(orientation="vertical"))
    translator = RecordingTranslator()
    artifact = pipeline([dialogue, sfx], translator).process(
        path,
        job_id="phase5-fixture",
        profile_fingerprint="sha256:" + "a" * 64,
        source_language="en",
        target_language="ar",
    )
    assert translator.inputs == ["HELLO FRIEND"]  # Ground-truth SFX never reaches translator.
    assert artifact.manifest["blocks"][1]["blockKind"] == "sfx"
    assert "translatedText" not in artifact.manifest["blocks"][1]
    assert artifact.manifest["blocks"][1]["processingAction"] == "preserve-original"

    after = Image.open(io.BytesIO(artifact.encoded)).convert("RGBA")
    # Independent ground-truth annotation, not a classifier-generated mask.
    gt_sfx = Image.new("L", before.size, 0)
    ImageDraw.Draw(gt_sfx).polygon(sfx.polygon, fill=255)
    before_sfx = Image.composite(before, Image.new("RGBA", before.size, (0, 0, 0, 0)), gt_sfx)
    after_sfx = Image.composite(after, Image.new("RGBA", after.size, (0, 0, 0, 0)), gt_sfx)
    assert all(high == 0 for _, high in ImageChops.difference(before_sfx, after_sfx).getextrema())

    # Dialogue region must actually change in this reference vertical slice.
    dialogue_mask = Image.new("L", before.size, 0)
    ImageDraw.Draw(dialogue_mask).polygon(dialogue.polygon, fill=255)
    before_dialogue = Image.composite(before, Image.new("RGBA", before.size, 0), dialogue_mask)
    after_dialogue = Image.composite(after, Image.new("RGBA", after.size, 0), dialogue_mask)
    assert any(high != 0 for _, high in ImageChops.difference(before_dialogue, after_dialogue).getextrema())


def test_uncertain_is_fail_closed_and_never_translated(tmp_path: Path):
    path = tmp_path / "uncertain.png"
    source_page(path)
    region = DetectedRegion("unknown", rect(40, 40, 220, 105), 0.8, text_hint="MAYBE")
    translator = RecordingTranslator()
    artifact = pipeline([region], translator).process(
        path, job_id="uncertain", profile_fingerprint="sha256:" + "b" * 64, source_language="en", target_language="ar"
    )
    assert translator.inputs == []
    block = artifact.manifest["blocks"][0]
    assert block["blockKind"] == "uncertain" and block["protectedFromEditing"] is True


def test_protected_overlap_fails_before_inpaint_or_render(tmp_path: Path):
    path = tmp_path / "conflict.png"
    source_page(path)
    dialogue = DetectedRegion("d", rect(120, 120, 310, 235), 0.99, text_hint="HELLO FRIEND", kind_hint="dialogue")
    sfx = DetectedRegion("s", rect(280, 175, 399, 279), 0.99, text_hint="BOOM", kind_hint="sfx")
    with pytest.raises(EngineApiError, match="protected") as exc:
        pipeline([dialogue, sfx], RecordingTranslator()).process(
            path, job_id="conflict", profile_fingerprint="sha256:" + "c" * 64, source_language="en", target_language="ar"
        )
    assert exc.value.code == "protected_region_conflict"


def test_reading_order_modes_are_deterministic():
    adapter = HeuristicReadingOrder()
    left = DetectedRegion("left", rect(20, 20, 80, 70), 1.0)
    right = DetectedRegion("right", rect(220, 20, 280, 70), 1.0)
    low = DetectedRegion("low", rect(120, 180, 180, 230), 1.0)
    assert [r.region_id for r in adapter.order([left, low, right], image_size=(320, 300), source_language="ja", layout_mode="manga-rtl")] == ["right", "left", "low"]
    assert [r.region_id for r in adapter.order([low, right, left], image_size=(320, 900), source_language="ko", layout_mode="webtoon-ttb")] == ["left", "right", "low"]


def test_ocr_routing_policy_matches_rev10():
    assert route_for_language("en") == ("ppocrv6-en-benchmark-winner",)
    assert route_for_language("ja") == ("benchmark-frozen-japanese-winner",)
    assert route_for_language("ko") == ("korean-ppocrv5-mobile-rec",)
    assert route_for_language("zh-Hans") == ("ppocrv6-zh-benchmark-winner",)


def test_manifest_validator_rejects_translated_sfx():
    payload = {
        "schemaVersion": 1,
        "jobId": "job",
        "profileFingerprint": "sha256:" + "d" * 64,
        "blocks": [{
            "blockId": "b1", "blockKind": "sfx", "processingAction": "preserve-original",
            "sourceText": "BOOM", "translatedText": "بوم", "confidence": 1.0,
            "polygon": [[1,1],[20,1],[20,20],[1,20]], "readingOrder": 0,
            "protectedFromEditing": True, "styleHint": {"align": "center"},
        }],
    }
    with pytest.raises(EngineApiError) as exc:
        validate_manifest(payload, width=100, height=100)
    assert exc.value.code == "invalid_result"


def test_arabic_renderer_raqm_self_test_and_mixed_direction():
    renderer = ArabicRenderer(arabic_font())
    renderer.self_test()
    image = Image.new("RGBA", (480, 180), "white")
    block = __import__("mte_engine.pipeline.contracts", fromlist=["EngineTextBlock"]).EngineTextBlock(
        block_id="b1", polygon=rect(20, 20, 460, 160), reading_order=0, source_text="source", source_confidence=1.0,
        source_language="en", block_kind="dialogue", processing_action="translate-replace", protected_from_editing=False,
        style_hints=StyleHints(), target_text="الإصدار 2.0 — HP +10", target_language="ar"
    )
    out = renderer.render(image, [block], protected_mask=Image.new("L", image.size, 0))
    assert any(high != 0 for _, high in ImageChops.difference(image, out).getextrema())
