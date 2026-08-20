import { describe, expect, it } from 'vitest';
import { CandidateAdmissionScheduler } from '../../src/queue/candidate-admission.js';
import { MemoryAdmissionController } from '../../src/queue/memory-admission.js';
import { buildSchedulingHint } from '../../src/queue/priority.js';
import type { JobRecord } from '../../src/pipeline/types.js';

describe('Phase 3 admission and memory backpressure', () => {
  it('keeps far webtoon candidates out of heavy admission', () => {
    const scheduler = new CandidateAdmissionScheduler();
    const jobs = Array.from({ length: 120 }, (_, index) => job(index, index < 2 ? 'visible' : index < 8 ? 'near' : 'far'));
    const decision = scheduler.select({ jobs, activeSessionId: 'ses-a', acquisitionCapacity: 2, preparedBySession: new Map() });
    expect(decision.admitted.length).toBe(2);
    expect(decision.admitted.every((item) => item.schedulingHint.visibility === 'visible')).toBe(true);
    expect(decision.admitted.some((item) => item.schedulingHint.visibility === 'far')).toBe(false);
  });

  it('runs a >64 MiB soft-budget reservation only when exclusive', async () => {
    const memory = new MemoryAdmissionController(64 * 1024 * 1024);
    const small = await memory.reserve(32 * 1024 * 1024);
    let largeStarted = false;
    const pending = memory.reserve(80 * 1024 * 1024).then((reservation) => {
      largeStarted = true;
      return reservation;
    });
    await Promise.resolve();
    expect(largeStarted).toBe(false);
    small.release();
    const large = await pending;
    expect(large.exclusive).toBe(true);
    large.release();
  });
});

function job(index: number, visibility: 'visible' | 'near' | 'far'): JobRecord {
  const now = Date.now() + index;
  return {
    jobId: `job-${index}`,
    runtimeSessionId: 'run-1',
    target: { sessionId: 'ses-a', tabId: 1, documentId: 'doc', candidateId: `cand-${index}`, sourceRevision: 1 },
    processingSpec: {} as JobRecord['processingSpec'],
    engineProfileFingerprint: 'engine',
    allowScreenshot: false,
    schedulingHint: buildSchedulingHint({ explicit: false, visibility, currentSession: true, readingOrder: index }),
    stage: 'waiting-admission',
    attempt: 0,
    cancelRequested: false,
    staleForDelivery: false,
    createdAt: now,
    updatedAt: now
  };
}
