export type Brand<T, Name extends string> = T & { readonly __brand: Name };

export type SessionId = Brand<string, 'SessionId'>;
export type CandidateId = Brand<string, 'CandidateId'>;
export type AcquisitionId = Brand<string, 'AcquisitionId'>;
export type BinaryId = Brand<string, 'BinaryId'>;
export type JobId = Brand<string, 'JobId'>;
export type WorkId = Brand<string, 'WorkId'>;
export type RuntimeSessionId = Brand<string, 'RuntimeSessionId'>;

function randomId(prefix: string): string {
  return `${prefix}_${crypto.randomUUID()}`;
}

export function newSessionId(): SessionId {
  return randomId('ses') as SessionId;
}

export function newCandidateId(): CandidateId {
  return randomId('cand') as CandidateId;
}

export function newAcquisitionId(): AcquisitionId {
  return randomId('acq') as AcquisitionId;
}

export function newBinaryId(): BinaryId {
  return randomId('bin') as BinaryId;
}

export function newJobId(): JobId {
  return randomId('job') as JobId;
}

export function newWorkId(): WorkId {
  return randomId('work') as WorkId;
}

export function workIdFromSignature(signature: string): WorkId {
  if (!/^[a-f0-9]{64}$/.test(signature)) throw new Error('Work signature must be a canonical SHA-256 hex string.');
  return `work_v1_${signature}` as WorkId;
}

export function newRuntimeSessionId(): RuntimeSessionId {
  return randomId('run') as RuntimeSessionId;
}
