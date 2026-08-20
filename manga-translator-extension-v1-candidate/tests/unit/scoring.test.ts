import { expect, it } from 'vitest';
import { applyGroupBoost, scoreCandidate } from '../../src/page/scoring.js';

it('large manga-like image outranks small UI icon', () => {
  const large = scoreCandidate({
    viewportWidth: 1200,
    viewportHeight: 900,
    rect: { x: 200, y: 0, width: 800, height: 1200 },
    naturalWidth: 1600,
    naturalHeight: 2400,
    visible: true,
    hidden: false,
    insideChromeUi: false,
    insideSemanticUi: false,
    likelyTrackingPixel: false,
    extensionOwned: false,
    sourceUrl: 'https://cdn.example/chapter/page-01.webp'
  });
  const icon = scoreCandidate({
    viewportWidth: 1200,
    viewportHeight: 900,
    rect: { x: 10, y: 10, width: 32, height: 32 },
    naturalWidth: 32,
    naturalHeight: 32,
    visible: true,
    hidden: false,
    insideChromeUi: true,
    insideSemanticUi: true,
    likelyTrackingPixel: false,
    extensionOwned: false,
    sourceUrl: 'https://reader.example/icon-user.png'
  });
  expect(large).toBeGreaterThan(icon);
  expect(large).toBeGreaterThan(0.5);
});

it('extension-owned and tracking pixels are hard rejected', () => {
  const base = {
    viewportWidth: 1000,
    viewportHeight: 800,
    rect: { x: 0, y: 0, width: 900, height: 1200 },
    visible: true,
    hidden: false,
    insideChromeUi: false,
    insideSemanticUi: false,
    likelyTrackingPixel: false,
    extensionOwned: false
  };
  expect(scoreCandidate({ ...base, extensionOwned: true })).toBe(0);
  expect(scoreCandidate({ ...base, likelyTrackingPixel: true })).toBe(0);
});

it('coherent reader group receives a boost', () => {
  const result = applyGroupBoost(
    Array.from({ length: 5 }, (_, index) => ({
      id: `p${index}`,
      parentKey: 'reader',
      sourceFamily: 'https://cdn.example/ch/10',
      centerX: 500 + (index % 2),
      width: 800,
      top: index * 1200,
      bottom: index * 1200 + 1150,
      baseScore: 0.4
    }))
  );
  expect(result.get('p0') ?? 0).toBeGreaterThan(0.55);
});
