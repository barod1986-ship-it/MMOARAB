import { sha256Bytes } from '../pipeline/sha256.js';

const encoder = new TextEncoder();

export async function deriveResultCacheKey(input: {
  sourceSha256: string;
  processingSpecFingerprint: string;
  engineProfileFingerprint: string;
}): Promise<string> {
  const canonical = [
    'mte-result-cache-v1',
    input.sourceSha256,
    input.processingSpecFingerprint,
    input.engineProfileFingerprint
  ].join('\0');
  return await sha256Bytes(encoder.encode(canonical));
}
