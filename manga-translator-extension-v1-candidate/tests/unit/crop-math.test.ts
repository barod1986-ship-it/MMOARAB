import { expect, it } from 'vitest';
import { computeScreenshotCrop } from '../../src/page/acquisition/crop-math.js';

it('maps CSS crop into actual screenshot bitmap scale', () => {
  const crop = computeScreenshotCrop(
    { x: 100, y: 50, width: 400, height: 300 },
    { width: 1000, height: 800, visualOffsetLeft: 0, visualOffsetTop: 0 },
    { width: 2000, height: 1600 }
  );
  expect(crop?.source).toEqual({ x: 200, y: 100, width: 800, height: 600 });
  expect(crop?.scaleX).toBe(2);
});

it('clips partially visible target and accounts for visual viewport offsets', () => {
  const crop = computeScreenshotCrop(
    { x: 20, y: 80, width: 300, height: 300 },
    { width: 500, height: 400, visualOffsetLeft: 50, visualOffsetTop: 100 },
    { width: 1000, height: 800 }
  );
  expect(crop?.targetVisibleRect).toEqual({ x: 50, y: 100, width: 270, height: 280 });
  expect(crop?.source).toEqual({ x: 0, y: 0, width: 540, height: 560 });
});

it('returns null when target is outside visible viewport', () => {
  expect(
    computeScreenshotCrop(
      { x: 1200, y: 900, width: 100, height: 100 },
      { width: 1000, height: 800, visualOffsetLeft: 0, visualOffsetTop: 0 },
      { width: 1000, height: 800 }
    )
  ).toBeNull();
});
