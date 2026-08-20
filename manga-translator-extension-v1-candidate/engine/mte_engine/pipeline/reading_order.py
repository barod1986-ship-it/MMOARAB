from __future__ import annotations

from collections.abc import Sequence

from .contracts import DetectedRegion, LayoutMode


class HeuristicReadingOrder:
    adapter_id = "heuristic-reading-order-v1"

    def order(
        self,
        regions: Sequence[DetectedRegion],
        *,
        image_size: tuple[int, int],
        source_language: str,
        layout_mode: LayoutMode,
    ) -> Sequence[DetectedRegion]:
        mode = _resolve_mode(layout_mode, source_language, image_size)
        if mode == "webtoon-ttb":
            return sorted(regions, key=lambda r: (_top(r), _left(r), r.region_id))
        if mode == "manga-rtl":
            # Y-overlap row clustering first, then right-to-left within each row.
            rows: list[list[DetectedRegion]] = []
            for region in sorted(regions, key=lambda r: (_top(r), -_right(r), r.region_id)):
                cy = (_top(region) + _bottom(region)) / 2
                placed = False
                for row in rows:
                    row_top = min(_top(item) for item in row)
                    row_bottom = max(_bottom(item) for item in row)
                    if row_top <= cy <= row_bottom:
                        row.append(region)
                        placed = True
                        break
                if not placed:
                    rows.append([region])
            ordered: list[DetectedRegion] = []
            for row in sorted(rows, key=lambda items: min(_top(item) for item in items)):
                ordered.extend(sorted(row, key=lambda r: (-_right(r), _top(r), r.region_id)))
            return ordered
        return sorted(regions, key=lambda r: (_top(r), _left(r), r.region_id))


def _resolve_mode(layout_mode: LayoutMode, source_language: str, image_size: tuple[int, int]) -> LayoutMode:
    if layout_mode != "auto":
        return layout_mode
    width, height = image_size
    if height >= width * 2.2:
        return "webtoon-ttb"
    if source_language == "ja":
        return "manga-rtl"
    return "western-ltr"


def _left(region: DetectedRegion) -> int:
    return min(point[0] for point in region.polygon)


def _right(region: DetectedRegion) -> int:
    return max(point[0] for point in region.polygon)


def _top(region: DetectedRegion) -> int:
    return min(point[1] for point in region.polygon)


def _bottom(region: DetectedRegion) -> int:
    return max(point[1] for point in region.polygon)
