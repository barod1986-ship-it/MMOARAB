import { AppError } from '../core/errors.js';
import type { AcquiredImage } from '../page/types.js';
import { validateImageBlob } from '../page/acquisition/image-utils.js';

const SOURCE_MIMES = new Set(['image/jpeg', 'image/png', 'image/webp', 'image/avif']);
const RESULT_MIMES = new Set(['image/webp', 'image/png']);

export async function validatePipelineSource(image: AcquiredImage, blob: Blob): Promise<{
  blob: Blob;
  mimeType: string;
  pixelWidth: number;
  pixelHeight: number;
}> {
  validateAuthority(image);
  const validated = await validateImageBlob(blob);
  if (!SOURCE_MIMES.has(validated.mimeType)) {
    throw new AppError('UNSUPPORTED_SOURCE_MIME', `Pipeline source MIME is not allowed in V1: ${validated.mimeType}.`);
  }
  if (image.mimeType && image.mimeType !== validated.mimeType) {
    // Sniffed bytes are authoritative. A mismatch is suspicious enough to reject the intake rather than silently relabel it.
    throw new AppError('NOT_AN_IMAGE', `Acquisition MIME metadata does not match source bytes (${image.mimeType} vs ${validated.mimeType}).`);
  }
  if (image.pixelWidth !== undefined && image.pixelWidth !== validated.width) {
    throw new AppError('SUSPECT_IMAGE_RESPONSE', 'Acquisition width metadata does not match decoded source bytes.');
  }
  if (image.pixelHeight !== undefined && image.pixelHeight !== validated.height) {
    throw new AppError('SUSPECT_IMAGE_RESPONSE', 'Acquisition height metadata does not match decoded source bytes.');
  }
  return {
    blob: validated.blob,
    mimeType: validated.mimeType,
    pixelWidth: validated.width,
    pixelHeight: validated.height
  };
}

export async function validatePipelineResult(input: {
  blob: Blob;
  expectedWidth: number;
  expectedHeight: number;
  encoderSemantics: string;
}): Promise<{ blob: Blob; mimeType: 'image/webp' | 'image/png'; pixelWidth: number; pixelHeight: number }> {
  const validated = await validateImageBlob(input.blob);
  if (!RESULT_MIMES.has(validated.mimeType)) {
    throw new AppError('UNSUPPORTED_RESULT_MIME', `Result MIME is not allowed in V1: ${validated.mimeType}.`);
  }
  if (input.encoderSemantics !== 'engine-exact-lossless-v1') {
    throw new AppError('UNSUPPORTED_RESULT_MIME', 'Result must declare a trusted exact-lossless encoder contract.');
  }
  if (validated.width !== input.expectedWidth || validated.height !== input.expectedHeight) {
    throw new AppError('RESULT_DIMENSIONS_MISMATCH', 'Result dimensions do not match the dimension-preserving ProcessingSpec.', {
      details: {
        expectedWidth: input.expectedWidth,
        expectedHeight: input.expectedHeight,
        actualWidth: validated.width,
        actualHeight: validated.height
      }
    });
  }
  return {
    blob: validated.blob,
    mimeType: validated.mimeType as 'image/webp' | 'image/png',
    pixelWidth: validated.width,
    pixelHeight: validated.height
  };
}

function validateAuthority(image: AcquiredImage): void {
  const ok =
    (image.method === 'dom-fetch' && image.authority === 'page-origin') ||
    (image.method === 'canvas-snapshot' && image.authority === 'page-origin') ||
    (image.method === 'extension-fetch' &&
      (image.authority === 'active-tab-main-origin' || image.authority === 'optional-exact-origin')) ||
    (image.method === 'viewport-capture' && image.authority === 'visual-capture');
  if (!ok) throw new AppError('BINARY_ACCESS_DENIED', 'Acquisition method/authority combination is invalid for trusted pipeline intake.');
}
