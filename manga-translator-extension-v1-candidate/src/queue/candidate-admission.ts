import { MAX_PREPARED_AHEAD_PER_SESSION } from '../shared/constants.js';
import type { JobRecord } from '../pipeline/types.js';
import { compareJobs } from './priority.js';

export type AdmissionDecision = {
  admitted: JobRecord[];
  deferred: JobRecord[];
};

export class CandidateAdmissionScheduler {
  select(input: {
    jobs: JobRecord[];
    activeSessionId?: string;
    acquisitionCapacity: number;
    preparedBySession: ReadonlyMap<string, number>;
    now?: number;
  }): AdmissionDecision {
    const now = input.now ?? Date.now();
    const candidates = input.jobs
      .filter((job) => job.stage === 'waiting-admission' && !job.cancelRequested && (job.notBefore ?? 0) <= now)
      .filter((job) => job.schedulingHint.priorityBand !== 'P6' || job.schedulingHint.explicit)
      .sort(compareJobs);

    const admitted: JobRecord[] = [];
    const deferred: JobRecord[] = [];
    const usedBySession = new Map<string, number>();
    let remaining = Math.max(0, input.acquisitionCapacity);

    // Fairness: inside each band, round-robin sessions while preserving reading order.
    for (const band of ['P0', 'P1', 'P2', 'P3', 'P4', 'P5', 'P6'] as const) {
      const inBand = candidates.filter((job) => job.schedulingHint.priorityBand === band);
      const perSession = new Map<string, JobRecord[]>();
      for (const job of inBand) {
        const bucket = perSession.get(job.target.sessionId) ?? [];
        bucket.push(job);
        perSession.set(job.target.sessionId, bucket);
      }
      for (const bucket of perSession.values()) bucket.sort(compareJobs);
      const sessionOrder = [...perSession.keys()].sort((a, b) => {
        if (a === input.activeSessionId) return -1;
        if (b === input.activeSessionId) return 1;
        const aFirst = perSession.get(a)?.[0];
        const bFirst = perSession.get(b)?.[0];
        return (aFirst?.createdAt ?? 0) - (bFirst?.createdAt ?? 0) || a.localeCompare(b);
      });

      let progressed = true;
      while (remaining > 0 && progressed) {
        progressed = false;
        for (const sessionId of sessionOrder) {
          if (remaining <= 0) break;
          const bucket = perSession.get(sessionId);
          const job = bucket?.shift();
          if (!job) continue;
          progressed = true;
          const prepared = (input.preparedBySession.get(sessionId) ?? 0) + (usedBySession.get(sessionId) ?? 0);
          const bypassPreparedLimit = job.schedulingHint.explicit || job.schedulingHint.visibility === 'visible';
          if (!bypassPreparedLimit && prepared >= MAX_PREPARED_AHEAD_PER_SESSION) {
            deferred.push(job);
            continue;
          }
          admitted.push(job);
          usedBySession.set(sessionId, (usedBySession.get(sessionId) ?? 0) + 1);
          remaining -= 1;
        }
      }
      for (const bucket of perSession.values()) deferred.push(...bucket);
      if (remaining <= 0) {
        for (const later of candidates) {
          if (!admitted.some((x) => x.jobId === later.jobId) && !deferred.some((x) => x.jobId === later.jobId)) deferred.push(later);
        }
        break;
      }
    }

    return { admitted, deferred };
  }
}
