import type { CandidateVisibility, JobRecord, PriorityBand, SchedulingHint } from '../pipeline/types.js';

const BAND_WEIGHT: Record<PriorityBand, number> = {
  P0: 0,
  P1: 1,
  P2: 2,
  P3: 3,
  P4: 4,
  P5: 5,
  P6: 6
};

export function priorityBand(input: {
  explicit: boolean;
  visibility: CandidateVisibility;
  currentSession: boolean;
  prefetch?: boolean;
}): PriorityBand {
  if (input.explicit) return 'P0';
  if (input.visibility === 'visible') return input.currentSession ? 'P1' : 'P2';
  if (input.visibility === 'near') return input.currentSession ? 'P3' : 'P4';
  if (input.prefetch) return 'P5';
  return 'P6';
}

export function compareJobs(a: JobRecord, b: JobRecord): number {
  const band = BAND_WEIGHT[a.schedulingHint.priorityBand] - BAND_WEIGHT[b.schedulingHint.priorityBand];
  if (band !== 0) return band;
  const age = a.createdAt - b.createdAt;
  if (age !== 0) return age;
  const order = a.schedulingHint.readingOrder - b.schedulingHint.readingOrder;
  if (order !== 0) return order;
  return a.jobId.localeCompare(b.jobId);
}

export function buildSchedulingHint(input: {
  explicit: boolean;
  visibility: CandidateVisibility;
  currentSession?: boolean;
  readingOrder?: number;
  estimatedSourceBytes?: number;
  acquisitionMethod?: SchedulingHint['acquisitionMethod'];
}): SchedulingHint {
  return {
    priorityBand: priorityBand({
      explicit: input.explicit,
      visibility: input.visibility,
      currentSession: input.currentSession ?? true
    }),
    visibility: input.visibility,
    readingOrder: input.readingOrder ?? Number.MAX_SAFE_INTEGER,
    explicit: input.explicit,
    ...(input.estimatedSourceBytes !== undefined ? { estimatedSourceBytes: input.estimatedSourceBytes } : {}),
    ...(input.acquisitionMethod ? { acquisitionMethod: input.acquisitionMethod } : {})
  };
}
