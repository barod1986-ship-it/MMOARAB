from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, Sequence

from PIL import Image

Point = tuple[int, int]
Polygon = tuple[Point, ...]
BlockKind = Literal["dialogue", "narration", "sfx", "other", "uncertain"]
ProcessingAction = Literal["translate-replace", "preserve-original"]
LayoutMode = Literal["auto", "manga-rtl", "webtoon-ttb", "western-ltr"]
Orientation = Literal["horizontal", "vertical"]


@dataclass(frozen=True, slots=True)
class StyleHints:
    orientation: Orientation = "horizontal"
    foreground: str = "#111111"
    outline: str = "#ffffff"
    align: Literal["start", "center", "end"] = "center"


@dataclass(frozen=True, slots=True)
class DetectedRegion:
    region_id: str
    polygon: Polygon
    confidence: float
    orientation_hint: Orientation = "horizontal"
    text_hint: str | None = None
    kind_hint: BlockKind | None = None
    style_hints: StyleHints = field(default_factory=StyleHints)


@dataclass(frozen=True, slots=True)
class OcrResult:
    text: str
    confidence: float
    source_language: str
    adapter_id: str


@dataclass(frozen=True, slots=True)
class RoleDecision:
    block_kind: BlockKind
    confidence: float
    processing_action: ProcessingAction
    protected_from_editing: bool


@dataclass(slots=True)
class EngineTextBlock:
    block_id: str
    polygon: Polygon
    reading_order: int
    source_text: str
    source_confidence: float
    source_language: str
    block_kind: BlockKind
    processing_action: ProcessingAction
    protected_from_editing: bool
    style_hints: StyleHints
    target_text: str | None = None
    target_language: str | None = None


@dataclass(frozen=True, slots=True)
class TranslationInputBlock:
    block_id: str
    source: str


@dataclass(frozen=True, slots=True)
class TranslatedBlock:
    block_id: str
    text: str


class DetectorAdapter(Protocol):
    adapter_id: str

    def detect(self, image: Image.Image, *, source_language: str, layout_mode: LayoutMode) -> Sequence[DetectedRegion]: ...


class ReadingOrderAdapter(Protocol):
    adapter_id: str

    def order(self, regions: Sequence[DetectedRegion], *, image_size: tuple[int, int], source_language: str, layout_mode: LayoutMode) -> Sequence[DetectedRegion]: ...


class OcrRouter(Protocol):
    adapter_id: str

    def recognize(self, image: Image.Image, region: DetectedRegion, *, source_language: str) -> OcrResult: ...


class BlockRoleClassifier(Protocol):
    adapter_id: str

    def classify(self, image: Image.Image, region: DetectedRegion, ocr: OcrResult) -> RoleDecision: ...


class TranslatorAdapter(Protocol):
    adapter_id: str

    def translate_page(
        self,
        *,
        source_language: str,
        target_language: str,
        blocks: Sequence[TranslationInputBlock],
    ) -> Sequence[TranslatedBlock]: ...


class InpainterAdapter(Protocol):
    adapter_id: str

    def inpaint(self, image: Image.Image, erase_mask: Image.Image) -> Image.Image: ...


class RendererAdapter(Protocol):
    adapter_id: str

    def render(self, image: Image.Image, blocks: Sequence[EngineTextBlock], *, protected_mask: Image.Image) -> Image.Image: ...
