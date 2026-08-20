import { AppError } from '../core/errors.js';

export async function sha256Blob(blob: Blob): Promise<string> {
  try {
    return await sha256Buffer(await blob.arrayBuffer());
  } catch (cause) {
    throw new AppError('HASH_FAILED', 'Failed to compute SHA-256 for staged binary.', { cause });
  }
}

export async function sha256Bytes(value: Uint8Array): Promise<string> {
  try {
    return await sha256Buffer(value);
  } catch (cause) {
    throw new AppError('HASH_FAILED', 'Failed to compute SHA-256 for pipeline identity.', { cause });
  }
}

export async function sha256Text(value: string): Promise<string> {
  try {
    return await sha256Buffer(new TextEncoder().encode(value));
  } catch (cause) {
    throw new AppError('HASH_FAILED', 'Failed to compute SHA-256 for pipeline identity.', { cause });
  }
}

async function sha256Buffer(data: BufferSource): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', data);
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, '0')).join('');
}
