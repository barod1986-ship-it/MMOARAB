import { MAX_SOURCE_BYTES } from '../../shared/constants.js';
import { AppError } from '../../core/errors.js';

export type ValidatedImageBlob = {
  blob: Blob;
  mimeType: string;
  width: number;
  height: number;
};

const ALLOWED_MIME = new Set([
  'image/png',
  'image/jpeg',
  'image/webp',
  'image/gif',
  'image/avif',
  'image/bmp'
]);

export async function validateImageBlob(blob: Blob): Promise<ValidatedImageBlob> {
  if (blob.size <= 0) throw new AppError('NOT_AN_IMAGE', 'Image payload is empty.');
  if (blob.size > MAX_SOURCE_BYTES) {
    throw new AppError('SOURCE_TOO_LARGE', 'Image source exceeds the 32 MiB V1 guard.', {
      details: { bytes: blob.size, limit: MAX_SOURCE_BYTES }
    });
  }

  const declared = normalizeMime(blob.type);
  const sniffed = await sniffRasterMime(blob);
  const mimeType = sniffed ?? (ALLOWED_MIME.has(declared) ? declared : '');
  if (!mimeType) {
    throw new AppError('NOT_AN_IMAGE', `Unsupported or unrecognized image payload (${declared || 'no MIME'}).`);
  }

  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(blob);
  } catch (cause) {
    throw new AppError('NOT_AN_IMAGE', 'Browser image decoder rejected the payload.', { cause });
  }
  const width = bitmap.width;
  const height = bitmap.height;
  bitmap.close();
  if (width <= 0 || height <= 0) throw new AppError('NOT_AN_IMAGE', 'Decoded image has zero dimensions.');
  return { blob: blob.type === mimeType ? blob : blob.slice(0, blob.size, mimeType), mimeType, width, height };
}

export async function responseToLimitedBlob(response: Response): Promise<Blob> {
  const lengthHeader = response.headers.get('content-length');
  if (lengthHeader) {
    const declared = Number(lengthHeader);
    if (Number.isFinite(declared) && declared > MAX_SOURCE_BYTES) {
      await response.body?.cancel();
      throw new AppError('SOURCE_TOO_LARGE', 'Remote image Content-Length exceeds the source guard.', {
        details: { bytes: declared, limit: MAX_SOURCE_BYTES }
      });
    }
  }

  const type = normalizeMime(response.headers.get('content-type') ?? '');
  if (isClearlyNonImageMime(type)) {
    await response.body?.cancel();
    throw new AppError('NOT_AN_IMAGE', `Remote response is clearly not an image (${type}).`);
  }

  if (!response.body) {
    const blob = await response.blob();
    if (blob.size > MAX_SOURCE_BYTES) throw new AppError('SOURCE_TOO_LARGE', 'Remote image exceeds source guard.');
    return blob.type ? blob : blob.slice(0, blob.size, type);
  }

  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!value) continue;
      total += value.byteLength;
      if (total > MAX_SOURCE_BYTES) {
        await reader.cancel('source-too-large');
        throw new AppError('SOURCE_TOO_LARGE', 'Remote image stream exceeded the 32 MiB source guard.', {
          details: { bytes: total, limit: MAX_SOURCE_BYTES }
        });
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  return new Blob(chunks, type ? { type } : undefined);
}

export function dimensionsAreSuspect(
  expectedWidth: number | undefined,
  expectedHeight: number | undefined,
  actualWidth: number,
  actualHeight: number
): boolean {
  if (!expectedWidth || !expectedHeight || expectedWidth <= 0 || expectedHeight <= 0) return false;
  const expectedRatio = expectedWidth / expectedHeight;
  const actualRatio = actualWidth / actualHeight;
  const ratioDelta = Math.abs(actualRatio - expectedRatio) / expectedRatio;
  // Density/srcset variants may have very different pixel sizes but should preserve aspect ratio.
  return ratioDelta > 0.12;
}

function normalizeMime(value: string): string {
  return value.split(';', 1)[0]?.trim().toLowerCase() ?? '';
}

function isClearlyNonImageMime(type: string): boolean {
  return (
    type.startsWith('text/') ||
    type === 'application/json' ||
    type === 'application/xml' ||
    type === 'text/html' ||
    type === 'application/xhtml+xml'
  );
}

async function sniffRasterMime(blob: Blob): Promise<string | null> {
  const bytes = new Uint8Array(await blob.slice(0, 32).arrayBuffer());
  if (bytes.length >= 8 && matches(bytes, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) return 'image/png';
  if (bytes.length >= 3 && matches(bytes, [0xff, 0xd8, 0xff])) return 'image/jpeg';
  if (bytes.length >= 6 && ascii(bytes, 0, 6).startsWith('GIF8')) return 'image/gif';
  if (bytes.length >= 12 && ascii(bytes, 0, 4) === 'RIFF' && ascii(bytes, 8, 4) === 'WEBP') return 'image/webp';
  if (bytes.length >= 2 && bytes[0] === 0x42 && bytes[1] === 0x4d) return 'image/bmp';
  if (bytes.length >= 12 && ascii(bytes, 4, 4) === 'ftyp') {
    const brand = ascii(bytes, 8, 4);
    if (brand === 'avif' || brand === 'avis') return 'image/avif';
  }
  return null;
}

function matches(bytes: Uint8Array, prefix: number[]): boolean {
  return prefix.every((value, index) => bytes[index] === value);
}

function ascii(bytes: Uint8Array, start: number, length: number): string {
  return String.fromCharCode(...bytes.slice(start, start + length));
}
