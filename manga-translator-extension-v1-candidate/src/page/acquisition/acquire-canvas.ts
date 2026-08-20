import { AppError } from '../../core/errors.js';
import type { AcquiredImage, PageImageCandidate } from '../types.js';
import { canvasToBlob } from './acquire-img.js';
import { validateImageBlob } from './image-utils.js';

export async function acquireCanvas(candidate: PageImageCandidate, canvas: HTMLCanvasElement): Promise<AcquiredImage> {
  if (canvas.width <= 0 || canvas.height <= 0) throw new AppError('CANVAS_EMPTY', 'Canvas has zero dimensions.', { retryable: true });
  try {
    const blob = await canvasToBlob(canvas, 'image/png');
    const validated = await validateImageBlob(blob);
    return {
      candidateId: candidate.candidateId,
      method: 'canvas-snapshot',
      blob: validated.blob,
      mimeType: validated.mimeType,
      pixelWidth: validated.width,
      pixelHeight: validated.height,
      authority: 'page-origin'
    };
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'SecurityError') {
      throw new AppError('CANVAS_TAINTED', 'Canvas pixels are tainted by cross-origin content.', { cause });
    }
    throw cause;
  }
}
