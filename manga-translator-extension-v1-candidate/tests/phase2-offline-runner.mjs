import assert from 'node:assert/strict';
import {
  DEFAULT_PROCESSING_SPEC,
  canonicalProcessingSpec,
  deriveWorkSignature,
  processingSpecFingerprint
} from '../.offline-check/pipeline/processing-spec.js';
import { sha256Text } from '../.offline-check/pipeline/sha256.js';
import { isTargetFresh } from '../.offline-check/pipeline/delivery-gate.js';

let passed = 0;
async function check(name, fn) {
  await fn();
  passed += 1;
  console.log(`ok p2-${passed} - ${name}`);
}

await check('SHA-256 is lowercase 64-char hex and stable', async () => {
  const first = await sha256Text('manga-translator-phase2');
  const second = await sha256Text('manga-translator-phase2');
  assert.match(first, /^[a-f0-9]{64}$/);
  assert.equal(first, second);
});

await check('ProcessingSpec canonical form freezes en→ar and SFX preserve semantics', async () => {
  const canonical = canonicalProcessingSpec(DEFAULT_PROCESSING_SPEC);
  const parsed = JSON.parse(canonical);
  assert.equal(parsed.sourceLanguage, 'en');
  assert.equal(parsed.targetLanguage, 'ar');
  assert.equal(parsed.textRolePolicy.sfxAction, 'preserve-original');
  assert.equal(parsed.textRolePolicy.uncertainAction, 'preserve-original');
  assert.equal(parsed.textRolePolicy.revision, 'sfx-preserve-v1');
  assert.equal(parsed.output.preserveDimensions, true);
});

await check('ProcessingSpec fingerprint is deterministic', async () => {
  const a = await processingSpecFingerprint(DEFAULT_PROCESSING_SPEC);
  const b = await processingSpecFingerprint(structuredClone(DEFAULT_PROCESSING_SPEC));
  assert.equal(a, b);
});

await check('WorkSignature changes with content or engine profile', async () => {
  const base = await deriveWorkSignature({
    sourceSha256: 'a'.repeat(64),
    processingSpec: DEFAULT_PROCESSING_SPEC,
    engineProfileFingerprint: 'mock-raster-png-v1'
  });
  const otherSource = await deriveWorkSignature({
    sourceSha256: 'b'.repeat(64),
    processingSpec: DEFAULT_PROCESSING_SPEC,
    engineProfileFingerprint: 'mock-raster-png-v1'
  });
  const otherProfile = await deriveWorkSignature({
    sourceSha256: 'a'.repeat(64),
    processingSpec: DEFAULT_PROCESSING_SPEC,
    engineProfileFingerprint: 'mock-raster-png-v2'
  });
  assert.notEqual(base, otherSource);
  assert.notEqual(base, otherProfile);
});

await check('delivery gate rejects stale sourceRevision and document identity', async () => {
  const target = { sessionId: 'session_1', tabId: 7, documentId: 'doc_1', candidateId: 'candidate_1', sourceRevision: 3 };
  const current = { status: 'active', sessionId: 'session_1', tabId: 7, documentId: 'doc_1', candidates: { candidate_1: { sourceRevision: 3 } } };
  assert.equal(isTargetFresh(current, target), true);
  assert.equal(isTargetFresh({ ...current, candidates: { candidate_1: { sourceRevision: 4 } } }, target), false);
  assert.equal(isTargetFresh({ ...current, documentId: 'doc_2' }, target), false);
});

console.log(`# ${passed} Phase 2 offline identity/delivery checks passed`);
