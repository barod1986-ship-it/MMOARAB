from __future__ import annotations

import math
import re
from collections.abc import Iterable

from PIL import Image

from .contracts import DetectedRegion, OcrResult, RoleDecision


ROLE_REVISION = "block-role-fail-closed-v1"
PRODUCTION_ROLE_REVISION = "visual-enclosure-sfx-guard-v1"

# These guards can only make a block *more* protected. They never grant destructive
# editing permission. Keep deliberately broad; false positives reduce translation
# coverage but cannot erase SFX/artwork.
_SHORT_SFX = frozenset(
    {
        "bam", "bang", "boom", "bump", "buzz", "click", "clack", "clang", "crack",
        "crash", "creak", "ding", "drip", "fwoosh", "gasp", "grr", "gulp", "hiss",
        "honk", "knock", "pop", "pow", "ring", "rustle", "slam", "snap", "splash",
        "splat", "squeak", "swish", "thud", "thump", "tick", "toc", "wham", "whizz",
        "whoosh", "zap", "zzt",
    }
)
_SFX_PUNCT_RE = re.compile(r"^[!?.…~〜ー—\-_*#]+$")
_REPEAT_RE = re.compile(r"(.)\1{2,}", re.IGNORECASE)


class ConservativeRoleClassifier:
    adapter_id = ROLE_REVISION

    def classify(self, image: Image.Image, region: DetectedRegion, ocr: OcrResult) -> RoleDecision:
        # Fixture/reference profile: hints are authoritative, unhinted stays protected.
        kind = region.kind_hint or "uncertain"
        confidence = 1.0 if region.kind_hint else 0.0
        if kind in {"dialogue", "narration"} and confidence >= 0.85:
            return RoleDecision(kind, confidence, "translate-replace", False)
        return RoleDecision(kind if kind in {"sfx", "other", "uncertain"} else "uncertain", confidence, "preserve-original", True)


class VisualEnclosureRoleClassifier:
    """Production V1 role gate with a strict, local grant model.

    The classifier does *not* try to prove that arbitrary text is not SFX. Instead it
    grants translate/replace only when OCR is strong and the text is visually enclosed
    by a quiet speech/narration region with a surrounding boundary. Any ambiguity is
    protected. The production benchmark/freeze remains the authority for release.
    """

    adapter_id = PRODUCTION_ROLE_REVISION

    def classify(self, image: Image.Image, region: DetectedRegion, ocr: OcrResult) -> RoleDecision:
        if region.kind_hint in {"sfx", "other", "uncertain"}:
            return RoleDecision(region.kind_hint, 1.0, "preserve-original", True)
        if region.kind_hint in {"dialogue", "narration"}:
            # A production detector-provided semantic hint may grant editing only with
            # high OCR confidence. The frozen detector benchmark still has to prove the
            # exact-zero SFX gate before this revision can ship.
            if ocr.confidence >= 0.85:
                return RoleDecision(region.kind_hint, min(1.0, ocr.confidence), "translate-replace", False)
            return RoleDecision("uncertain", ocr.confidence, "preserve-original", True)

        if ocr.confidence < 0.85 or not ocr.text.strip():
            return RoleDecision("uncertain", max(0.0, min(1.0, ocr.confidence)), "preserve-original", True)
        if _lexically_protect(ocr.text):
            return RoleDecision("sfx", 0.90, "preserve-original", True)

        evidence = _enclosure_evidence(image, region)
        if evidence is None:
            return RoleDecision("uncertain", 0.0, "preserve-original", True)
        quiet_fraction, boundary_fraction, background_mad = evidence

        # Fixed thresholds are part of PRODUCTION_ROLE_REVISION. Changing any of them
        # requires a new revision and benchmark/freeze rather than silent tuning.
        if quiet_fraction >= 0.84 and boundary_fraction >= 0.62 and background_mad <= 13.0:
            visual = min(1.0, (quiet_fraction + boundary_fraction) / 2.0)
            confidence = min(float(ocr.confidence), visual)
            if confidence >= 0.85:
                return RoleDecision("dialogue", confidence, "translate-replace", False)
        return RoleDecision("uncertain", min(float(ocr.confidence), max(quiet_fraction, boundary_fraction)), "preserve-original", True)


def _lexically_protect(text: str) -> bool:
    normalized = " ".join(text.strip().split())
    if not normalized:
        return True
    token = normalized.casefold().strip(".!?…~〜ー—-_*#'\"")
    if token in _SHORT_SFX:
        return True
    if _SFX_PUNCT_RE.fullmatch(normalized):
        return True
    if len(normalized) <= 16 and _REPEAT_RE.search(normalized):
        return True
    # Very short single-token display text is common for SFX. Preserving it is safer
    # than granting a destructive edit; multi-word dialogue remains eligible.
    if len(token) <= 3 and token.isalpha() and " " not in normalized:
        return True
    return False


def _enclosure_evidence(image: Image.Image, region: DetectedRegion) -> tuple[float, float, float] | None:
    try:
        import numpy as np
    except ImportError:
        # Missing optional production math support must reduce capability, never grant
        # destructive editing permission or break the fixture/core Engine at import time.
        return None
    xs = [p[0] for p in region.polygon]
    ys = [p[1] for p in region.polygon]
    if not xs or not ys:
        return None
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    width = max(1.0, float(right - left + 1))
    height = max(1.0, float(bottom - top + 1))
    cx = (left + right) / 2.0
    cy = (top + bottom) / 2.0

    # Speech bubbles/narration boxes can be substantially larger than the OCR box.
    rx = min(max(width * 2.8, 28.0), 320.0)
    ry = min(max(height * 2.8, 28.0), 320.0)
    x0 = max(0, int(math.floor(cx - rx)))
    y0 = max(0, int(math.floor(cy - ry)))
    x1 = min(image.width, int(math.ceil(cx + rx + 1)))
    y1 = min(image.height, int(math.ceil(cy + ry + 1)))
    if x1 - x0 < 12 or y1 - y0 < 12:
        return None

    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)

    # Sample a near-text annulus while excluding the OCR polygon/bbox itself. A quiet
    # dominant colour is typical of speech/narration containers; detailed artwork is not.
    inner_x = max(width * 0.62, 4.0)
    inner_y = max(height * 0.62, 4.0)
    outer_x = max(width * 1.25, 12.0)
    outer_y = max(height * 1.25, 12.0)
    samples: list[np.ndarray] = []
    for yy in range(max(0, int(cy - outer_y)), min(image.height, int(cy + outer_y + 1))):
        dy = abs(yy - cy)
        for xx in range(max(0, int(cx - outer_x)), min(image.width, int(cx + outer_x + 1))):
            dx = abs(xx - cx)
            if dx <= inner_x and dy <= inner_y:
                continue
            samples.append(rgb[yy, xx])
    if len(samples) < 64:
        return None
    values = np.stack(samples, axis=0)
    median = np.median(values, axis=0)
    distances = np.max(np.abs(values - median), axis=1)
    quiet_fraction = float(np.mean(distances <= 26.0))
    background_mad = float(np.median(distances))

    # Closed-boundary evidence: rays leave the OCR box and must encounter a strong
    # contrast from the quiet interior. Random artwork can create hits, but combining
    # this with the quiet-annulus test intentionally makes the grant conservative.
    ray_hits = 0
    ray_total = 16
    for i in range(ray_total):
        angle = (2.0 * math.pi * i) / ray_total
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        hit = False
        for step in np.linspace(1.35, 4.8, 36):
            xx = int(round(cx + cos_a * (width / 2.0) * step))
            yy = int(round(cy + sin_a * (height / 2.0) * step))
            if xx < 0 or yy < 0 or xx >= image.width or yy >= image.height:
                break
            pixel = rgb[yy, xx]
            if float(np.max(np.abs(pixel - median))) >= 58.0:
                hit = True
                break
        if hit:
            ray_hits += 1
    boundary_fraction = ray_hits / ray_total
    return quiet_fraction, boundary_fraction, background_mad
