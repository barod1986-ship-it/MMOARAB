import { AppError } from '../../core/errors.js';
import type { AcquiredImage, PageImageCandidate } from '../types.js';
import { responseToLimitedBlob, validateImageBlob } from './image-utils.js';

const MAX_CANVAS_PIXELS = 100_000_000;

export async function acquireImageDirect(candidate: PageImageCandidate, img: HTMLImageElement, signal?: AbortSignal): Promise<AcquiredImage> {
  const sourceUrl = candidate.sourceUrl;
  if (!sourceUrl) throw new AppError('CANDIDATE_NOT_READY', 'Image has no resolved source URL.', { retryable: true });

  try {
    const response = await fetch(sourceUrl, {
      method: 'GET',
      credentials: 'same-origin',
      redirect: 'follow',
      cache: 'default',
      ...(signal ? { signal } : {})
    });
    if (!response.ok) throw new AppError('REMOTE_FETCH_FAILED', `Page-context fetch returned HTTP ${response.status}.`);
    const raw = await responseToLimitedBlob(response);
    const validated = await validateImageBlob(raw);
    return {
      candidateId: candidate.candidateId,
      method: 'dom-fetch',
      blob: validated.blob,
      mimeType: validated.mimeType,
      pixelWidth: validated.width,
      pixelHeight: validated.height,
      sourceUrl,
      authority: 'page-origin'
    };
  } catch (fetchError) {
    if (signal?.aborted) throw new AppError('STALE_SESSION', 'Image acquisition was cancelled with the PageSession.');
    try {
      return await snapshotLoadedImage(candidate, img);
    } catch (snapshotError) {
      throw new AppError('REMOTE_FETCH_FAILED', 'Direct image acquisition failed in the page context.', {
        retryable: true,
        cause: { fetchError, snapshotError }
      });
    }
  }
}

export async function snapshotLoadedImage(candidate: PageImageCandidate, img: HTMLImageElement): Promise<AcquiredImage> {
  if (!img.complete || img.naturalWidth <= 0 || img.naturalHeight <= 0) {
    throw new AppError('CANDIDATE_NOT_READY', 'Image has not finished loading.', { retryable: true });
  }
  if (img.naturalWidth * img.naturalHeight > MAX_CANVAS_PIXELS) {
    throw new AppError('SOURCE_TOO_LARGE', 'Loaded image is too large for the V1 canvas snapshot guard.');
  }
  try {
    await img.decode();
  } catch {
    // Some already-decoded images reject decode() after state changes; dimensions remain the gate here.
  }

  const canvas = document.createElement('canvas');
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  const context = canvas.getContext('2d', { alpha: true });
  if (!context) throw new AppError('CANVAS_EMPTY', '2D canvas context is unavailable.');
  try {
    context.drawImage(img, 0, 0, canvas.width, canvas.height);
    const blob = await canvasToBlob(canvas, 'image/png');
    const validated = await validateImageBlob(blob);
    return {
      candidateId: candidate.candidateId,
      method: 'canvas-snapshot',
      blob: validated.blob,
      mimeType: validated.mimeType,
      pixelWidth: validated.width,
      pixelHeight: validated.height,
      ...(candidate.sourceUrl ? { sourceUrl: candidate.sourceUrl } : {}),
      authority: 'page-origin'
    };
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'SecurityError') {
      throw new AppError('CANVAS_TAINTED', 'Loaded image cannot be read because the canvas is tainted.', { cause });
    }
    throw cause;
  } finally {
    canvas.width = 0;
    canvas.height = 0;
  }
}

export function canvasToBlob(canvas: HTMLCanvasElement, type: string): Promise<Blob> {
  return new Promise((resolve, reject) => {
    try {
      canvas.toBlob((blob) => {
        if (blob) resolve(blob);
        else reject(new AppError('CANVAS_EMPTY', 'Canvas encoder returned null.'));
      }, type);
    } catch (cause) {
      reject(cause);
    }
  });
}
