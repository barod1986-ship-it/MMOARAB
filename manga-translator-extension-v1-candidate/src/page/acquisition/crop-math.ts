import type { RectSnapshot, ViewportSnapshot } from '../types.js';

export type BitmapSize = { width: number; height: number };
export type CropPlan = {
  source: { x: number; y: number; width: number; height: number };
  targetVisibleRect: RectSnapshot;
  scaleX: number;
  scaleY: number;
};

export function computeScreenshotCrop(
  targetRect: RectSnapshot,
  viewport: ViewportSnapshot,
  bitmap: BitmapSize
): CropPlan | null {
  if (viewport.width <= 0 || viewport.height <= 0 || bitmap.width <= 0 || bitmap.height <= 0) return null;

  const visibleBounds: RectSnapshot = {
    x: viewport.visualOffsetLeft,
    y: viewport.visualOffsetTop,
    width: viewport.width,
    height: viewport.height
  };
  const visible = intersect(targetRect, visibleBounds);
  if (!visible) return null;

  const scaleX = bitmap.width / viewport.width;
  const scaleY = bitmap.height / viewport.height;
  const sx = Math.max(0, Math.floor((visible.x - viewport.visualOffsetLeft) * scaleX));
  const sy = Math.max(0, Math.floor((visible.y - viewport.visualOffsetTop) * scaleY));
  const ex = Math.min(bitmap.width, Math.ceil((visible.x + visible.width - viewport.visualOffsetLeft) * scaleX));
  const ey = Math.min(bitmap.height, Math.ceil((visible.y + visible.height - viewport.visualOffsetTop) * scaleY));
  if (ex <= sx || ey <= sy) return null;

  return {
    source: { x: sx, y: sy, width: ex - sx, height: ey - sy },
    targetVisibleRect: visible,
    scaleX,
    scaleY
  };
}

function intersect(a: RectSnapshot, b: RectSnapshot): RectSnapshot | null {
  const x1 = Math.max(a.x, b.x);
  const y1 = Math.max(a.y, b.y);
  const x2 = Math.min(a.x + a.width, b.x + b.width);
  const y2 = Math.min(a.y + a.height, b.y + b.height);
  if (x2 <= x1 || y2 <= y1) return null;
  return { x: x1, y: y1, width: x2 - x1, height: y2 - y1 };
}
