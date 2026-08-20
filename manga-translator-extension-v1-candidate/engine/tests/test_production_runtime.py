from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from mte_engine.config import EngineSettings
from mte_engine.benchmark.common import canonical_json, sha256_path
from mte_engine.benchmark.manual_artifacts import derivation_digest
from mte_engine.errors import EngineApiError
from mte_engine.pipeline.contracts import DetectedRegion, OcrResult, TranslationInputBlock
from mte_engine.pipeline.detector import ProductionDetector
from mte_engine.pipeline.ocr import ProductionOcrRouter
from mte_engine.pipeline.inpaint import ProductionInpainter, INPAINT_SELECTION_REVISION
from mte_engine.pipeline.roles import ConservativeRoleClassifier, PRODUCTION_ROLE_REVISION, VisualEnclosureRoleClassifier
from mte_engine.pipeline.translator import (
    OPENAI_PRIVACY_MODE,
    OPENAI_TRANSLATOR_ADAPTER,
    OpenAIResponsesTranslator,
    production_translation_support,
)
from mte_engine.production_runtime import assess_production_runtime


def _region() -> DetectedRegion:
    return DetectedRegion("r1", ((2, 2), (22, 2), (22, 12), (2, 12)), 0.9)


def test_paddle_detector_uses_frozen_local_model_and_parses_polygons(tmp_path: Path):
    model_dir = tmp_path / "det"
    model_dir.mkdir()

    class FakeModel:
        def predict(self, **kwargs):
            assert kwargs["batch_size"] == 1
            return [{"res": {"dt_polys": [[[1, 1], [18, 1], [18, 9], [1, 9]]], "dt_scores": [0.93]}}]

    detector = ProductionDetector(candidate_id="ppocrv6-medium-detector-run", model_path=model_dir, model_factory=lambda _: FakeModel())
    regions = detector.detect(Image.new("RGB", (30, 20), "white"), source_language="en", layout_mode="auto")
    assert len(regions) == 1
    assert regions[0].polygon == ((1, 1), (18, 1), (18, 9), (1, 9))
    assert regions[0].confidence == pytest.approx(0.93)
    assert regions[0].kind_hint is None



def test_both_v1_paddle_detector_candidates_are_runtime_supported(tmp_path: Path):
    model_dir = tmp_path / "det"
    model_dir.mkdir()

    class FakeModel:
        def predict(self, **kwargs):
            return []

    for candidate_id in ("ppocrv6-small-detector-run", "ppocrv6-medium-detector-run"):
        detector = ProductionDetector(candidate_id=candidate_id, model_path=model_dir, model_factory=lambda _: FakeModel())
        assert detector.detect(Image.new("RGB", (20, 20), "white"), source_language="en", layout_mode="auto") == ()

def test_detector_refuses_unimplemented_benchmark_winner(tmp_path: Path):
    model_dir = tmp_path / "det"
    model_dir.mkdir()
    with pytest.raises(EngineApiError, match="not implemented"):
        ProductionDetector(candidate_id="comic-specialized-detector-run", model_path=model_dir)


def test_paddle_ocr_uses_candidate_selected_for_language(tmp_path: Path):
    model_dir = tmp_path / "rec"
    model_dir.mkdir()

    class FakeRecognizer:
        def predict(self, **kwargs):
            return [{"res": {"rec_text": "  HELLO   WORLD ", "rec_score": 0.88}}]

    router = ProductionOcrRouter(
        selected={
            "ocrEnglish": "ppocrv6-medium-en",
            "ocrJapanese": "ppocrv6-ja-fallback",
            "ocrKorean": "ppocrv5-ko",
            "ocrChinese": "ppocrv6-medium-zh",
        },
        artifact_paths={
            "ppocrv6-medium-rec": model_dir,
            "ppocrv5-korean-mobile-rec": model_dir,
        },
        paddle_factory=lambda _: FakeRecognizer(),
    )
    result = router.recognize(Image.new("RGB", (40, 30), "white"), _region(), source_language="en")
    assert result.text == "HELLO WORLD"
    assert result.confidence == pytest.approx(0.88)
    assert result.source_language == "en"
    assert "ppocrv6-medium-en" in result.adapter_id


def test_manga_ocr_is_local_path_bound_and_does_not_invent_native_score(tmp_path: Path):
    model_dir = tmp_path / "manga"
    model_dir.mkdir()
    router = ProductionOcrRouter(
        selected={
            "ocrEnglish": "ppocrv6-medium-en",
            "ocrJapanese": "manga-ocr-ja",
            "ocrKorean": "ppocrv5-ko",
            "ocrChinese": "ppocrv6-medium-zh",
        },
        artifact_paths={"manga-ocr-base-0.1.16": model_dir},
        manga_factory=lambda _: (lambda image: "  こんにちは   世界  "),
    )
    result = router.recognize(Image.new("RGB", (40, 30), "white"), _region(), source_language="ja")
    assert result.text == "こんにちは 世界"
    assert result.confidence == 0.5
    assert "no-native-score" in result.adapter_id


def test_production_ocr_refuses_implicit_auto_language(tmp_path: Path):
    router = ProductionOcrRouter(selected={}, artifact_paths={})
    with pytest.raises(EngineApiError, match="explicit supported language"):
        router.recognize(Image.new("RGB", (30, 20), "white"), _region(), source_language="auto")


def test_unhinted_role_remains_protected_so_real_detector_cannot_translate_sfx_by_default():
    decision = ConservativeRoleClassifier().classify(
        Image.new("RGB", (30, 20), "white"),
        _region(),
        OcrResult("BOOM", 0.99, "en", "test"),
    )
    assert decision.block_kind == "uncertain"
    assert decision.processing_action == "preserve-original"
    assert decision.protected_from_editing is True




def _bubble_image() -> Image.Image:
    image = Image.new("RGB", (180, 120), (145, 150, 155))
    draw = ImageDraw.Draw(image)
    draw.ellipse((20, 18, 160, 100), fill="white", outline="black", width=3)
    draw.rectangle((70, 55, 110, 58), fill="black")
    return image


def test_production_role_gate_grants_only_strongly_enclosed_dialogue():
    region = DetectedRegion("r1", ((68, 48), (112, 48), (112, 64), (68, 64)), 0.95)
    decision = VisualEnclosureRoleClassifier().classify(
        _bubble_image(), region, OcrResult("HELLO FRIEND", 0.97, "en", "test")
    )
    assert decision.block_kind == "dialogue"
    assert decision.processing_action == "translate-replace"
    assert decision.protected_from_editing is False


def test_production_role_gate_preserves_sfx_even_inside_a_bubble_like_shape():
    region = DetectedRegion("r1", ((68, 48), (112, 48), (112, 64), (68, 64)), 0.95)
    decision = VisualEnclosureRoleClassifier().classify(
        _bubble_image(), region, OcrResult("BOOM", 0.99, "en", "test")
    )
    assert decision.block_kind == "sfx"
    assert decision.processing_action == "preserve-original"
    assert decision.protected_from_editing is True


def test_production_role_gate_preserves_unenclosed_text_even_with_strong_ocr():
    image = Image.new("RGB", (180, 120), "white")
    region = DetectedRegion("r1", ((68, 48), (112, 48), (112, 64), (68, 64)), 0.95)
    decision = VisualEnclosureRoleClassifier().classify(
        image, region, OcrResult("HELLO FRIEND", 0.99, "en", "test")
    )
    assert decision.processing_action == "preserve-original"
    assert decision.protected_from_editing is True


def _write_inpaint_contract(model_dir: Path, candidate_id: str = "lama-inpaint") -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "model.onnx"
    model_path.write_bytes(b"fake-onnx")
    model_sha = sha256_path(model_path)
    derivation = {
        "schemaVersion": 1,
        "packagerRevision": "rev10-inpaint-onnx-packager-v1",
        "artifactId": "lama-big" if candidate_id == "lama-inpaint" else "aot-gan-places2",
        "candidateId": candidate_id,
        "runtimeContract": INPAINT_SELECTION_REVISION,
        "sourceArtifactSha256": "sha256:" + "1" * 64,
        "sourceReviewRecordId": "source-review-test",
        "sourceReviewFileSha256": "sha256:" + "2" * 64,
        "converterReviewRecordId": "converter-review-test",
        "converterReviewFileSha256": "sha256:" + "4" * 64,
        "converterRevision": "converter-test",
        "converterSourceUrl": "https://example.invalid/converter",
        "converterSourceSha256": "sha256:" + "3" * 64,
        "modelSha256": model_sha,
        "createdAtUtc": "2026-08-19T12:00:00Z",
        "operator": "unit-test",
        "runtimeValidation": {"validatedProvider": "CPUExecutionProvider", "smokeShapes": [[1,3,64,80],[1,3,96,112]]},
    }
    derivation["derivationSha256"] = derivation_digest(derivation)
    derivation_path = model_dir / "mte-derivation.json"
    derivation_path.write_bytes(canonical_json(derivation))
    (model_dir / "mte-inpaint-contract.json").write_bytes(canonical_json({
        "schemaVersion": 1,
        "contract": INPAINT_SELECTION_REVISION,
        "candidateId": candidate_id,
        "modelFile": "model.onnx",
        "imageInput": "image",
        "maskInput": "mask",
        "output": "output",
        "tensorLayout": "NCHW",
        "imageRange": "0..1-rgb",
        "maskSemantics": "1=erase",
        "padMultiple": 8,
        "modelSha256": model_sha,
        "derivationManifest": "mte-derivation.json",
        "derivationManifestSha256": sha256_path(derivation_path),
    }))


def test_production_inpainter_changes_only_erase_mask_pixels(tmp_path: Path):
    model_dir = tmp_path / "lama"
    _write_inpaint_contract(model_dir)

    class Meta:
        def __init__(self, name: str):
            self.name = name

    class FakeSession:
        def get_inputs(self):
            return [Meta("image"), Meta("mask")]

        def get_outputs(self):
            return [Meta("output")]

        def run(self, outputs, feeds):
            image = feeds["image"].copy()
            image[:, 0, :, :] = 1.0
            image[:, 1:, :, :] = 0.0
            return [image]

    inpainter = ProductionInpainter(
        candidate_id="lama-inpaint",
        model_dir=model_dir,
        session_factory=lambda path, providers: FakeSession(),
    )
    source = Image.new("RGBA", (19, 13), (10, 20, 30, 255))
    mask = Image.new("L", source.size, 0)
    ImageDraw.Draw(mask).rectangle((5, 4, 8, 7), fill=255)
    result = inpainter.inpaint(source, mask)
    assert result.size == source.size
    assert result.getpixel((0, 0)) == (10, 20, 30, 255)
    assert result.getpixel((6, 5)) == (255, 0, 0, 255)
    assert result.getpixel((9, 5)) == (10, 20, 30, 255)


def test_production_inpainter_refuses_model_hash_drift_inside_materialized_package(tmp_path: Path):
    model_dir = tmp_path / "lama"
    _write_inpaint_contract(model_dir)
    (model_dir / "model.onnx").write_bytes(b"tampered")
    with pytest.raises(EngineApiError, match="model hash"):
        ProductionInpainter(candidate_id="lama-inpaint", model_dir=model_dir, session_factory=lambda path, providers: None)


def test_production_inpainter_refuses_derivation_manifest_hash_drift(tmp_path: Path):
    model_dir = tmp_path / "lama"
    _write_inpaint_contract(model_dir)
    with (model_dir / "mte-derivation.json").open("ab") as h:
        h.write(b" ")
    with pytest.raises(EngineApiError, match="derivation manifest"):
        ProductionInpainter(candidate_id="lama-inpaint", model_dir=model_dir, session_factory=lambda path, providers: None)


def test_production_inpainter_refuses_wrong_contract_candidate(tmp_path: Path):
    model_dir = tmp_path / "lama"
    _write_inpaint_contract(model_dir, candidate_id="aot-inpaint")
    with pytest.raises(EngineApiError, match="candidateId"):
        ProductionInpainter(
            candidate_id="lama-inpaint",
            model_dir=model_dir,
            session_factory=lambda path, providers: object(),
        )




def test_production_inpainter_refuses_cross_family_derivation_artifact(tmp_path: Path):
    model_dir = tmp_path / "lama"
    _write_inpaint_contract(model_dir, candidate_id="lama-inpaint")
    derivation_path = model_dir / "mte-derivation.json"
    derivation = json.loads(derivation_path.read_text(encoding="utf-8"))
    derivation["artifactId"] = "aot-gan-places2"
    derivation["derivationSha256"] = derivation_digest(derivation)
    derivation_path.write_bytes(canonical_json(derivation))
    contract_path = model_dir / "mte-inpaint-contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["derivationManifestSha256"] = sha256_path(derivation_path)
    contract_path.write_bytes(canonical_json(contract))
    with pytest.raises(EngineApiError, match="derivation identity"):
        ProductionInpainter(
            candidate_id="lama-inpaint",
            model_dir=model_dir,
            session_factory=lambda path, providers: object(),
        )


def test_production_role_gate_missing_numpy_fails_closed(monkeypatch):
    import builtins
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "numpy":
            raise ImportError("simulated")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    region = DetectedRegion("r1", ((68, 48), (112, 48), (112, 64), (68, 64)), 0.95)
    decision = VisualEnclosureRoleClassifier().classify(
        _bubble_image(), region, OcrResult("HELLO FRIEND", 0.99, "en", "test")
    )
    assert decision.processing_action == "preserve-original"
    assert decision.protected_from_editing is True


def test_openai_translator_sends_text_only_and_requires_exact_ids():
    captured: dict[str, object] = {}

    def request(url: str, headers: dict[str, str], payload: bytes, timeout: float):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = json.loads(payload)
        body = json.dumps({"translations": [{"id": "b2", "text": "الثاني"}, {"id": "b1", "text": "الأول"}]}, ensure_ascii=False)
        response = {"status": "completed", "output": [{"content": [{"type": "output_text", "text": body}]}]}
        return 200, json.dumps(response, ensure_ascii=False).encode()

    translator = OpenAIResponsesTranslator(api_key="secret-key", model="gpt-5.4-mini-2026-03-17", request_fn=request)
    translated = translator.translate_page(
        source_language="en",
        target_language="ar",
        blocks=[TranslationInputBlock("b1", "first"), TranslationInputBlock("b2", "second")],
    )
    assert [(x.block_id, x.text) for x in translated] == [("b1", "الأول"), ("b2", "الثاني")]
    request_body = captured["body"]
    assert isinstance(request_body, dict)
    assert request_body["store"] is False
    serialized = json.dumps(request_body, ensure_ascii=False)
    assert "first" in serialized and "second" in serialized
    assert "image" not in serialized.lower()
    assert "polygon" not in serialized.lower()
    assert captured["url"] == "https://api.openai.com/v1/responses"


def test_openai_translator_rejects_missing_or_extra_ids():
    def request(url: str, headers: dict[str, str], payload: bytes, timeout: float):
        body = json.dumps({"translations": [{"id": "wrong", "text": "خطأ"}]}, ensure_ascii=False)
        return 200, json.dumps({"status": "completed", "output": [{"content": [{"type": "output_text", "text": body}]}]}).encode()

    translator = OpenAIResponsesTranslator(api_key="secret-key", model="gpt-5.4-mini-2026-03-17", request_fn=request)
    with pytest.raises(EngineApiError, match="unknown or duplicate"):
        translator.translate_page(source_language="en", target_language="ar", blocks=[TranslationInputBlock("b1", "first")])


def test_translation_freeze_support_requires_dated_model_and_exact_privacy_mode():
    ok, reason, leaves = production_translation_support({
        "adapterId": OPENAI_TRANSLATOR_ADAPTER,
        "modelOrProviderRevision": "gpt-5.4-mini-2026-03-17",
        "privacyMode": OPENAI_PRIVACY_MODE,
        "roleClassifierRevision": "future-role-v1",
    })
    assert ok and reason is None and leaves is True
    ok, _, _ = production_translation_support({
        "adapterId": OPENAI_TRANSLATOR_ADAPTER,
        "modelOrProviderRevision": "gpt-5.4-mini",
        "privacyMode": OPENAI_PRIVACY_MODE,
    })
    assert not ok


def test_runtime_assessment_names_role_and_inpaint_as_remaining_real_blockers(tmp_path: Path):
    settings = EngineSettings(data_dir=tmp_path, external_text_translation_enabled=True, openai_api_key="secret")
    freeze = {
        "selected": {
            "detector": "ppocrv6-medium-detector-run",
            "ocrEnglish": "ppocrv6-medium-en",
            "ocrJapanese": "ppocrv6-ja-fallback",
            "ocrKorean": "ppocrv5-ko",
            "ocrChinese": "ppocrv6-medium-zh",
            "inpainter": "lama-inpaint",
        },
        "translation": {
            "adapterId": OPENAI_TRANSLATOR_ADAPTER,
            "modelOrProviderRevision": "gpt-5.4-mini-2026-03-17",
            "privacyMode": OPENAI_PRIVACY_MODE,
            "roleClassifierRevision": "block-role-fail-closed-v1",
        },
    }
    assessment = assess_production_runtime(settings, freeze)
    assert assessment.state == "runtime-unavailable"
    assert assessment.text_leaves_device is True
    joined = "\n".join(assessment.reasons)
    assert "role/SFX classifier" in joined
    assert "ONNX Runtime production inpainting dependency" in joined


def test_api_key_is_not_exposed_by_settings_repr(tmp_path: Path):
    settings = EngineSettings(data_dir=tmp_path, openai_api_key="super-secret")
    assert "super-secret" not in repr(settings)


def test_model_archive_materialization_is_digest_addressed_and_traversal_safe(tmp_path: Path):
    import hashlib
    import zipfile
    from mte_engine.production_runtime import materialize_model_directory

    archive = tmp_path / "model.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("model/inference.pdmodel", b"model-bytes")
        zf.writestr("model/inference.pdiparams", b"params")
    digest = "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest()
    settings = EngineSettings(data_dir=tmp_path / "data")
    materialized = materialize_model_directory(settings, artifact_id="ppocr-test", source=archive, expected_sha256=digest)
    assert materialized.name == "model"
    assert (materialized / "inference.pdmodel").read_bytes() == b"model-bytes"
    # A second call reuses the digest-addressed immutable cache rather than re-extracting elsewhere.
    assert materialize_model_directory(settings, artifact_id="ppocr-test", source=archive, expected_sha256=digest) == materialized

    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("../escape.txt", b"no")
    bad_digest = "sha256:" + hashlib.sha256(bad.read_bytes()).hexdigest()
    with pytest.raises(EngineApiError, match="unsafe path"):
        materialize_model_directory(settings, artifact_id="bad", source=bad, expected_sha256=bad_digest)
    assert not (tmp_path / "escape.txt").exists()
