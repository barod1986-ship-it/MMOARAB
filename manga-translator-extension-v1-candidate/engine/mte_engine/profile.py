from __future__ import annotations

import hashlib
import json
from pathlib import Path

import PIL
from PIL import features

from .benchmark.common import sha256_path
from .benchmark.freeze import load_freeze
from .config import EngineSettings
from .constants import FIXTURE_PROFILE_ID, PROFILE_ID, PROFILE_REVISION
from .pipeline.detector import DETECTOR_SELECTION_REVISION
from .pipeline.inpaint import INPAINT_SELECTION_REVISION
from .pipeline.ocr import ROUTING_REVISION
from .pipeline.reading_order import HeuristicReadingOrder
from .pipeline.renderer import LAYOUT_REVISION, RENDERER_REVISION
from .pipeline.roles import ROLE_REVISION
from .pipeline.translator import TRANSLATION_SCHEMA_REVISION, production_translation_support


def _feature_version(name: str) -> str | None:
    try:
        value = features.version(name)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, str) and value else None


def _font_digest(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    return sha256_path(path)


def _bundled_freeze_path() -> Path:
    return Path(__file__).resolve().parent / "benchmark" / "production-profile-freeze.json"


def _freeze_path(settings: EngineSettings | None = None, explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit
    if settings is not None and settings.production_freeze_path is not None:
        return settings.production_freeze_path
    return _bundled_freeze_path()


def current_profile_fingerprint(
    profile_id: str = PROFILE_ID,
    *,
    font_path: Path | None = None,
    freeze_path: Path | None = None,
) -> str:
    if profile_id not in {PROFILE_ID, FIXTURE_PROFILE_ID}:
        raise ValueError(f"Unknown profile: {profile_id}")
    common = {
        "protocolSemantics": 1,
        "pipelineRevision": PROFILE_REVISION,
        "profileId": profile_id,
        "pillowVersion": PIL.__version__,
        "imageCodecVersions": {
            "webp": _feature_version("webp"),
            "zlib": _feature_version("zlib"),
            "jpeg": _feature_version("jpg"),
            "libjpegTurbo": _feature_version("libjpeg_turbo"),
            "avif": _feature_version("avif"),
            "raqm": _feature_version("raqm"),
            "freetype2": _feature_version("freetype2"),
        },
        "textRolePolicy": "sfx-preserve-v1",
        "readingOrder": HeuristicReadingOrder.adapter_id,
        "renderer": {
            "adapter": RENDERER_REVISION,
            "layout": LAYOUT_REVISION,
            "fontArtifactSha256": _font_digest(font_path),
        },
        "encoder": {
            "policy": "webp-lossless-exact-then-png-lossless-v1",
            "exactLosslessRequired": True,
            "protectedPixelVerification": "post-encode-decode-v1",
        },
    }
    if profile_id == FIXTURE_PROFILE_ID:
        common.update({
            "detector": "reference-fixture-detector-v1",
            "ocrRouter": "reference-ocr-router-v1",
            "blockRoleClassifier": ROLE_REVISION,
            "translator": "reference-arabic-translator-v1",
            "inpainter": "reference-solid-inpaint-v1",
            "developmentOnly": True,
        })
    else:
        freeze = load_freeze(_freeze_path(explicit=freeze_path))
        common.update({
            "detector": DETECTOR_SELECTION_REVISION,
            "ocrRouter": ROUTING_REVISION,
            "blockRoleClassifier": (freeze.get("translation", {}).get("roleClassifierRevision") if freeze else "production-role-selection-pending"),
            "translator": {
                "schema": TRANSLATION_SCHEMA_REVISION,
                "freeze": freeze.get("translation") if freeze else {"status": "production-translation-selection-pending"},
            },
            "inpainter": INPAINT_SELECTION_REVISION,
            "benchmarkFreeze": (
                {
                    "status": "approved",
                    "freezeSha256": freeze["freezeSha256"],
                    "reportSha256": freeze["reportSha256"],
                    "selected": freeze["selected"],
                    "selectedArtifacts": freeze["selectedArtifacts"],
                    "runtime": freeze["runtime"],
                    "translation": freeze["translation"],
                    "rendererFreeze": freeze["renderer"],
                }
                if freeze else {"status": "production-model-selection-pending"}
            ),
        })
    canonical = json.dumps(common, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _all_pinned_artifacts_present(settings: EngineSettings, freeze: dict[str, object]) -> bool:
    base = settings.model_artifacts_dir
    pins = freeze.get("selectedArtifacts")
    if base is None or not isinstance(pins, list) or not pins:
        return False
    for pin in pins:
        if not isinstance(pin, dict):
            return False
        filename = pin.get("expectedFilename")
        expected = pin.get("sha256")
        if not isinstance(filename, str) or not isinstance(expected, str):
            return False
        path = base / filename
        try:
            if not path.exists() or sha256_path(path) != expected:
                return False
        except (OSError, ValueError):
            return False
    return True


def _configured_font_matches_freeze(settings: EngineSettings, freeze: dict[str, object]) -> bool:
    if settings.arabic_font_path is None or not settings.arabic_font_path.is_file():
        return False
    renderer = freeze.get("renderer")
    pins = freeze.get("selectedArtifacts")
    if not isinstance(renderer, dict) or not isinstance(pins, list):
        return False
    font_id = renderer.get("fontArtifactId")
    pin = next((item for item in pins if isinstance(item, dict) and item.get("artifactId") == font_id), None)
    if not isinstance(pin, dict) or not isinstance(pin.get("sha256"), str):
        return False
    try:
        return sha256_path(settings.arabic_font_path) == pin["sha256"]
    except (OSError, ValueError):
        return False


def profile_state(profile_id: str, settings: EngineSettings) -> str:
    if settings.arabic_font_path is None or not settings.arabic_font_path.is_file() or not features.check("raqm"):
        return "renderer-missing"
    if profile_id == FIXTURE_PROFILE_ID:
        return "ready" if settings.enable_fixture_profile else "unavailable-hardware"
    freeze = load_freeze(_freeze_path(settings=settings))
    if freeze is None:
        return "needs-download"
    if not _all_pinned_artifacts_present(settings, freeze):
        return "needs-download"
    if not _configured_font_matches_freeze(settings, freeze):
        return "renderer-missing"
    # Freeze, artifacts and renderer are necessary but runtime support is independent.
    # A benchmark winner is never silently swapped for an implemented alternative.
    from .production_runtime import assess_production_runtime
    return assess_production_runtime(settings, freeze).state


def _production_privacy(settings: EngineSettings) -> dict[str, bool | None]:
    freeze = load_freeze(_freeze_path(settings=settings))
    if freeze is None:
        return {"imageLeavesDevice": False, "ocrTextLeavesDevice": None, "visualContextLeavesDevice": False}
    supported, _, text_leaves = production_translation_support(freeze.get("translation"))
    return {
        "imageLeavesDevice": False,
        "ocrTextLeavesDevice": text_leaves if supported else None,
        "visualContextLeavesDevice": False,
    }


def _production_external_providers(settings: EngineSettings) -> list[str]:
    freeze = load_freeze(_freeze_path(settings=settings))
    if freeze is None:
        return []
    supported, _, text_leaves = production_translation_support(freeze.get("translation"))
    return ["OpenAI"] if supported and text_leaves else []


def profile_descriptors(settings: EngineSettings) -> list[dict[str, object]]:
    freeze_path = _freeze_path(settings=settings)
    descriptors = [{
        "profileId": PROFILE_ID,
        "profileFingerprint": current_profile_fingerprint(PROFILE_ID, font_path=settings.arabic_font_path, freeze_path=freeze_path),
        "state": profile_state(PROFILE_ID, settings),
        "privacy": _production_privacy(settings),
        "externalProviders": _production_external_providers(settings),
    }]
    if settings.enable_fixture_profile:
        descriptors.append({
            "profileId": FIXTURE_PROFILE_ID,
            "profileFingerprint": current_profile_fingerprint(FIXTURE_PROFILE_ID, font_path=settings.arabic_font_path, freeze_path=freeze_path),
            "state": profile_state(FIXTURE_PROFILE_ID, settings),
            "privacy": {"imageLeavesDevice": False, "ocrTextLeavesDevice": False, "visualContextLeavesDevice": False},
            "externalProviders": [],
        })
    return descriptors


def ready_profile_fingerprints(settings: EngineSettings) -> set[str]:
    return {item["profileFingerprint"] for item in profile_descriptors(settings) if item["state"] == "ready"}


def get_profile_descriptor(settings: EngineSettings, profile_id: str) -> dict[str, object]:
    for descriptor in profile_descriptors(settings):
        if descriptor["profileId"] == profile_id:
            return descriptor
    raise KeyError(profile_id)
