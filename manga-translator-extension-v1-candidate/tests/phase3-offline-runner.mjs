import assert from 'node:assert/strict';
import { deriveResultCacheKey } from '../.offline-check/cache/cache-key.js';
import { CandidateAdmissionScheduler } from '../.offline-check/queue/candidate-admission.js';
import { MemoryAdmissionController } from '../.offline-check/queue/memory-admission.js';
import { buildSchedulingHint, priorityBand } from '../.offline-check/queue/priority.js';
import { workIdFromSignature } from '../.offline-check/shared/ids.js';

let passed = 0;
async function check(name, fn) {
  await fn();
  passed += 1;
  console.log(`ok p3-${passed} - ${name}`);
}

await check('cache key is content/spec/profile identity, never URL identity', async () => {
  const base = await deriveResultCacheKey({
    sourceSha256: 'a'.repeat(64),
    processingSpecFingerprint: 'b'.repeat(64),
    engineProfileFingerprint: 'engine-v1'
  });
  const same = await deriveResultCacheKey({
    sourceSha256: 'a'.repeat(64),
    processingSpecFingerprint: 'b'.repeat(64),
    engineProfileFingerprint: 'engine-v1'
  });
  const profileChange = await deriveResultCacheKey({
    sourceSha256: 'a'.repeat(64),
    processingSpecFingerprint: 'b'.repeat(64),
    engineProfileFingerprint: 'engine-v2'
  });
  assert.match(base, /^[a-f0-9]{64}$/);
  assert.equal(base, same);
  assert.notEqual(base, profileChange);
});

await check('priority bands preserve visible-over-near-over-far invariants', async () => {
  assert.equal(priorityBand({ explicit: true, visibility: 'far', currentSession: true }), 'P0');
  assert.equal(priorityBand({ explicit: false, visibility: 'visible', currentSession: true }), 'P1');
  assert.equal(priorityBand({ explicit: false, visibility: 'near', currentSession: true }), 'P3');
  assert.equal(priorityBand({ explicit: false, visibility: 'far', currentSession: true }), 'P6');
});

await check('100+ discovered candidates remain metadata-only unless admitted', async () => {
  const scheduler = new CandidateAdmissionScheduler();
  const jobs = Array.from({ length: 120 }, (_, index) => fakeJob(index, index < 2 ? 'visible' : index < 8 ? 'near' : 'far'));
  const decision = scheduler.select({
    jobs,
    activeSessionId: 'ses-a',
    acquisitionCapacity: 2,
    preparedBySession: new Map()
  });
  assert.equal(decision.admitted.length, 2);
  assert.equal(decision.admitted.every((job) => job.schedulingHint.visibility === 'visible'), true);
  assert.equal(decision.deferred.length, 6);
  assert.equal(decision.admitted.some((job) => job.schedulingHint.visibility === 'far'), false);
});

await check('admission fairness round-robins sessions inside one band', async () => {
  const scheduler = new CandidateAdmissionScheduler();
  const jobs = [
    fakeJob(0, 'near', 'ses-b'),
    fakeJob(1, 'near', 'ses-b'),
    fakeJob(2, 'near', 'ses-c'),
    fakeJob(3, 'near', 'ses-c')
  ];
  const decision = scheduler.select({ jobs, activeSessionId: 'ses-a', acquisitionCapacity: 2, preparedBySession: new Map() });
  assert.deepEqual(new Set(decision.admitted.map((job) => job.target.sessionId)), new Set(['ses-b', 'ses-c']));
});

await check('memory budget backpressures concurrent reservations and allows large item exclusively', async () => {
  const memory = new MemoryAdmissionController(64 * 1024 * 1024);
  const first = await memory.reserve(40 * 1024 * 1024);
  let secondGranted = false;
  const secondPromise = memory.reserve(30 * 1024 * 1024).then((reservation) => {
    secondGranted = true;
    return reservation;
  });
  await Promise.resolve();
  assert.equal(secondGranted, false);
  first.release();
  const second = await secondPromise;
  assert.equal(secondGranted, true);
  second.release();
  const huge = await memory.reserve(80 * 1024 * 1024);
  assert.equal(huge.exclusive, true);
  huge.release();
});

await check('work owner id is deterministic from canonical work signature', async () => {
  const signature = '9'.repeat(64);
  assert.equal(workIdFromSignature(signature), `work_v1_${signature}`);
  assert.throws(() => workIdFromSignature('not-a-signature'));
});

function fakeJob(index, visibility, sessionId = 'ses-a') {
  return {
    jobId: `job-${index}`,
    runtimeSessionId: 'run-1',
    target: { sessionId, tabId: sessionId === 'ses-a' ? 1 : 2, documentId: 'doc', candidateId: `cand-${index}`, sourceRevision: 1 },
    processingSpec: {},
    engineProfileFingerprint: 'engine',
    allowScreenshot: false,
    schedulingHint: buildSchedulingHint({ explicit: false, visibility, currentSession: sessionId === 'ses-a', readingOrder: index }),
    stage: 'waiting-admission',
    attempt: 0,
    cancelRequested: false,
    staleForDelivery: false,
    createdAt: index,
    updatedAt: index
  };
}

console.log(`# ${passed} Phase 3 offline queue/cache identity checks passed`);
