import { sendMessage } from '../../messaging/protocol.js';
import { exactOriginPattern } from './remote-policy.js';
import type { AcquisitionOutcome } from '../types.js';

export async function hasExactOriginPermission(sessionId: string, candidateId: string, origin: string): Promise<boolean> {
  const pattern = exactOriginPattern(origin);
  if (!pattern) return false;
  const result = await sendMessage('background:has-origin', { sessionId, candidateId, origin });
  return result.granted;
}

export async function acquireViaBackground(data: {
  sessionId: string;
  candidateId: string;
  sourceUrl: string;
  forPresentation: boolean;
}): Promise<AcquisitionOutcome> {
  return await sendMessage('background:fetch-candidate', data);
}
