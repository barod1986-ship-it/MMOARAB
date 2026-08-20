import assert from 'node:assert/strict';
import { buildSourceKey, getSourceOrigin, resolveSourceFromValues, sourceFamily } from '../.offline-check/page/source-resolver.js';
import { applyGroupBoost, scoreCandidate } from '../.offline-check/page/scoring.js';
import { computeScreenshotCrop } from '../.offline-check/page/acquisition/crop-math.js';
import { evaluateRemotePolicy, exactOriginPattern } from '../.offline-check/page/acquisition/remote-policy.js';

let passed = 0;
function check(name, fn) {
  fn();
  passed += 1;
  console.log(`ok ${passed} - ${name}`);
}

check('currentSrc wins over src/lazy hints', () => {
  assert.equal(resolveSourceFromValues({ currentSrc: '/large.webp', src: '/small.webp', lazy: { 'data-src': '/lazy.webp' } }, 'https://reader.example/chapter/1'), 'https://reader.example/large.webp');
});
check('known lazy source resolves relative to base URL', () => {
  assert.equal(resolveSourceFromValues({ currentSrc: '', src: '', lazy: { 'data-lazy-src': '../img/p17.jpg' } }, 'https://reader.example/c/10/'), 'https://reader.example/c/img/p17.jpg');
});
check('blob URL is not treated as host origin and URL family groups directory', () => {
  assert.equal(getSourceOrigin('blob:https://reader.example/123'), null);
  assert.equal(sourceFamily('https://cdn.example/ch/10/page-17.webp?x=1'), 'https://cdn.example/ch/10');
});
check('source keys are PageSession scoped', () => {
  assert.notEqual(buildSourceKey('a', 'img', 'https://x/y'), buildSourceKey('b', 'img', 'https://x/y'));
});
check('large content outranks UI icon', () => {
  const large = scoreCandidate({ viewportWidth: 1200, viewportHeight: 900, rect: { x: 200, y: 0, width: 800, height: 1200 }, naturalWidth: 1600, naturalHeight: 2400, visible: true, hidden: false, insideChromeUi: false, insideSemanticUi: false, likelyTrackingPixel: false, extensionOwned: false, sourceUrl: 'https://cdn.example/chapter/page-01.webp' });
  const icon = scoreCandidate({ viewportWidth: 1200, viewportHeight: 900, rect: { x: 10, y: 10, width: 32, height: 32 }, naturalWidth: 32, naturalHeight: 32, visible: true, hidden: false, insideChromeUi: true, insideSemanticUi: true, likelyTrackingPixel: false, extensionOwned: false, sourceUrl: 'https://reader.example/icon-user.png' });
  assert.ok(large > icon && large > 0.5);
});
check('tracking/extension-owned images are hard rejected', () => {
  const base = { viewportWidth: 1000, viewportHeight: 800, rect: { x: 0, y: 0, width: 900, height: 1200 }, visible: true, hidden: false, insideChromeUi: false, insideSemanticUi: false, likelyTrackingPixel: false, extensionOwned: false };
  assert.equal(scoreCandidate({ ...base, extensionOwned: true }), 0);
  assert.equal(scoreCandidate({ ...base, likelyTrackingPixel: true }), 0);
});
check('coherent reader group boosts confidence', () => {
  const result = applyGroupBoost(Array.from({ length: 5 }, (_, index) => ({ id: `p${index}`, parentKey: 'reader', sourceFamily: 'https://cdn.example/ch/10', centerX: 500 + (index % 2), width: 800, top: index * 1200, bottom: index * 1200 + 1150, baseScore: 0.4 })));
  assert.ok((result.get('p0') ?? 0) > 0.55);
});
check('screenshot crop scales CSS pixels to bitmap pixels', () => {
  const crop = computeScreenshotCrop({ x: 100, y: 50, width: 400, height: 300 }, { width: 1000, height: 800, visualOffsetLeft: 0, visualOffsetTop: 0 }, { width: 2000, height: 1600 });
  assert.deepEqual(crop?.source, { x: 200, y: 100, width: 800, height: 600 });
});
check('visual viewport offsets clip correctly', () => {
  const crop = computeScreenshotCrop({ x: 20, y: 80, width: 300, height: 300 }, { width: 500, height: 400, visualOffsetLeft: 50, visualOffsetTop: 100 }, { width: 1000, height: 800 });
  assert.deepEqual(crop?.targetVisibleRect, { x: 50, y: 100, width: 270, height: 280 });
});
check('external CDN requires exact-origin grant', () => {
  assert.deepEqual(evaluateRemotePolicy({ candidateUrl: 'https://cdn.example/p1.webp', knownCandidateUrl: 'https://cdn.example/p1.webp', sessionMainOrigin: 'https://reader.example', exactOriginGranted: false }), { allowed: false, reason: 'permission-needed', origin: 'https://cdn.example' });
});
check('redirect cannot silently widen authority', () => {
  assert.deepEqual(evaluateRemotePolicy({ candidateUrl: 'https://cdn.example/p1.webp', knownCandidateUrl: 'https://cdn.example/p1.webp', sessionMainOrigin: 'https://reader.example', exactOriginGranted: true, finalResponseUrl: 'https://other.example/p1.webp', finalOriginGranted: false }), { allowed: false, reason: 'permission-needed', origin: 'https://other.example' });
});
check('redirect target works only after its own exact-origin grant', () => {
  assert.deepEqual(evaluateRemotePolicy({ candidateUrl: 'https://cdn.example/p1.webp', knownCandidateUrl: 'https://cdn.example/p1.webp', sessionMainOrigin: 'https://reader.example', exactOriginGranted: true, finalResponseUrl: 'https://other.example/p1.webp', finalOriginGranted: true }), { allowed: true, authority: 'optional-exact-origin', requestOrigin: 'https://other.example' });
});
check('external HTTP CDN is rejected', () => {
  assert.deepEqual(evaluateRemotePolicy({ candidateUrl: 'http://cdn.example/p1.webp', knownCandidateUrl: 'http://cdn.example/p1.webp', sessionMainOrigin: 'https://reader.example', exactOriginGranted: true }), { allowed: false, reason: 'invalid-url' });
});
check('remote URL must exactly match known candidate', () => {
  assert.deepEqual(evaluateRemotePolicy({ candidateUrl: 'https://cdn.example/p2.webp', knownCandidateUrl: 'https://cdn.example/p1.webp', sessionMainOrigin: 'https://reader.example', exactOriginGranted: true }), { allowed: false, reason: 'candidate-mismatch' });
});
check('exact optional origin pattern only accepts HTTPS', () => {
  assert.equal(exactOriginPattern('https://cdn.example'), 'https://cdn.example/*');
  assert.equal(exactOriginPattern('http://cdn.example'), null);
});
console.log(`# ${passed} offline checks passed`);
