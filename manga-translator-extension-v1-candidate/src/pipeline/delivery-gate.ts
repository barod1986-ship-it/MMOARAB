import type { JobRecord, PageTargetRef } from './types.js';

type DeliverySessionView = {
  status: string;
  sessionId: string;
  tabId: number;
  documentId?: string;
  candidates: Record<string, { sourceRevision: number }>;
};

export function isTargetFresh(session: DeliverySessionView | null, target: PageTargetRef): boolean {
  if (!session || session.status !== 'active') return false;
  if (session.sessionId !== target.sessionId || session.tabId !== target.tabId) return false;
  if (session.documentId !== target.documentId) return false;
  const candidate = session.candidates[target.candidateId];
  return Boolean(candidate && candidate.sourceRevision === target.sourceRevision);
}

export function isJobFreshForDelivery(session: DeliverySessionView | null, job: Pick<JobRecord, 'target'>): boolean {
  return isTargetFresh(session, job.target);
}
