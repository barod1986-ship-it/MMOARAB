import { browser } from 'wxt/browser';
import { AppError } from './errors.js';
import { newAcquisitionId } from '../shared/ids.js';
import type { AcquisitionOutcome, AcquiredImage, RectSnapshot, ViewportSnapshot } from '../page/types.js';
import { computeScreenshotCrop } from '../page/acquisition/crop-math.js';
import { MAX_SOURCE_BYTES, SCREENSHOT_MIN_START_INTERVAL_MS } from '../shared/constants.js';
import { dimensionsAreSuspect, responseToLimitedBlob, validateImageBlob } from '../page/acquisition/image-utils.js';
import { evaluateRemotePolicy, exactOriginPattern } from '../page/acquisition/remote-policy.js';
import type { StoredPageSession } from './session-store.js';

export class AcquisitionHandoffStore {
  readonly #items = new Map<string, { sessionId: string; image: AcquiredImage & { blob: Blob } }>();
  readonly #order: string[] = [];
  readonly #maxItems: number;
  readonly #maxBytes: number;
  #storedBytes = 0;

  constructor(maxItems = 12, maxBytes = 128 * 1024 * 1024) {
    this.#maxItems = maxItems;
    this.#maxBytes = maxBytes;
  }

  put(sessionId: string, image: AcquiredImage & { blob: Blob }): string {
    const id = newAcquisitionId();
    this.#items.set(id, { sessionId, image });
    this.#order.push(id);
    this.#storedBytes += image.blob.size;

    while (this.#order.length > this.#maxItems || this.#storedBytes > this.#maxBytes) {
      const oldest = this.#order.shift();
      if (!oldest) break;
      this.#drop(oldest);
    }
    return id;
  }

  getOwned(acquisitionId: string, sessionId: string, candidateId: string): (AcquiredImage & { blob: Blob }) | null {
    const record = this.#items.get(acquisitionId);
    if (!record || record.sessionId !== sessionId || record.image.candidateId !== candidateId) return null;
    return record.image;
  }

  release(acquisitionId: string): void {
    this.#drop(acquisitionId);
    const index = this.#order.indexOf(acquisitionId);
    if (index >= 0) this.#order.splice(index, 1);
  }

  #drop(acquisitionId: string): void {
    const record = this.#items.get(acquisitionId);
    if (record) this.#storedBytes -= record.image.blob.size;
    this.#items.delete(acquisitionId);
  }
}

export async function fetchKnownCandidate(options: {
  session: StoredPageSession;
  candidateId: string;
  sourceUrl: string;
  forPresentation: boolean;
  acquisitionStore: AcquisitionHandoffStore;
  sessionStillActive?(): Promise<boolean>;
}): Promise<AcquisitionOutcome> {
  const known = options.session.candidates[options.candidateId];
  if (!known || !known.sourceUrl) return failed(options.candidateId, 'CANDIDATE_NOT_FOUND', 'Candidate is not registered in the active PageSession.');

  const candidateUrl = canonicalUrl(options.sourceUrl);
  const knownUrl = canonicalUrl(known.sourceUrl);
  if (!candidateUrl || !knownUrl || candidateUrl !== knownUrl) {
    return failed(options.candidateId, 'REMOTE_FETCH_BLOCKED', 'Requested URL does not match the registered candidate source.');
  }

  const sourceOrigin = new URL(candidateUrl).origin;
  const exactGranted = sourceOrigin === options.session.mainFrameOrigin ? false : await containsExactOrigin(sourceOrigin);
  const initialPolicy = evaluateRemotePolicy({
    candidateUrl,
    knownCandidateUrl: knownUrl,
    sessionMainOrigin: options.session.mainFrameOrigin,
    exactOriginGranted: exactGranted
  });
  if (!initialPolicy.allowed) {
    if (initialPolicy.reason === 'permission-needed' && initialPolicy.origin) {
      return permissionNeeded(options.candidateId, initialPolicy.origin);
    }
    return failed(options.candidateId, 'REMOTE_FETCH_BLOCKED', `Remote fetch policy rejected request: ${initialPolicy.reason}.`);
  }

  try {
    const response = await fetch(candidateUrl, {
      method: 'GET',
      credentials: 'omit',
      redirect: 'follow',
      cache: 'no-store'
    });
    if (!response.ok) {
      await response.body?.cancel();
      return failed(options.candidateId, 'REMOTE_FETCH_FAILED', `Remote image fetch returned HTTP ${response.status}.`);
    }

    let finalOriginGranted = false;
    try {
      const finalOrigin = new URL(response.url).origin;
      if (finalOrigin !== sourceOrigin && finalOrigin !== options.session.mainFrameOrigin) {
        finalOriginGranted = await containsExactOrigin(finalOrigin);
      }
    } catch {
      // The policy validator below owns malformed final URL handling.
    }
    const finalPolicy = evaluateRemotePolicy({
      candidateUrl,
      knownCandidateUrl: knownUrl,
      sessionMainOrigin: options.session.mainFrameOrigin,
      exactOriginGranted: exactGranted,
      finalResponseUrl: response.url,
      finalOriginGranted
    });
    if (!finalPolicy.allowed) {
      await response.body?.cancel();
      if (finalPolicy.reason === 'permission-needed' && finalPolicy.origin) {
        return permissionNeeded(options.candidateId, finalPolicy.origin);
      }
      return failed(options.candidateId, 'REMOTE_FETCH_BLOCKED', `Redirect policy rejected response: ${finalPolicy.reason}.`);
    }

    const rawBlob = await responseToLimitedBlob(response);
    const validated = await validateImageBlob(rawBlob);
    if (dimensionsAreSuspect(known.naturalWidth, known.naturalHeight, validated.width, validated.height)) {
      return failed(options.candidateId, 'SUSPECT_IMAGE_RESPONSE', 'Remote response aspect ratio differs strongly from the displayed candidate.');
    }

    if (options.sessionStillActive && !(await options.sessionStillActive())) {
      return failed(options.candidateId, 'STALE_SESSION', 'PageSession changed before remote acquisition completed.');
    }

    const stored: AcquiredImage & { blob: Blob } = {
      candidateId: options.candidateId,
      method: 'extension-fetch',
      blob: validated.blob,
      mimeType: validated.mimeType,
      pixelWidth: validated.width,
      pixelHeight: validated.height,
      sourceUrl: candidateUrl,
      authority: finalPolicy.authority
    };
    const acquisitionId = options.acquisitionStore.put(options.session.sessionId, stored);
    return {
      ok: true,
      image: {
        candidateId: stored.candidateId,
        method: stored.method,
        acquisitionId,
        ...(options.forPresentation ? { blob: stored.blob } : {}),
        mimeType: stored.mimeType,
        pixelWidth: validated.width,
        pixelHeight: validated.height,
        sourceUrl: candidateUrl,
        authority: finalPolicy.authority
      }
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown remote fetch failure.';
    return failed(options.candidateId, error instanceof AppError ? error.code : 'REMOTE_FETCH_FAILED', message);
  }
}

let lastCaptureAt = 0;

export async function captureKnownCandidate(options: {
  session: StoredPageSession;
  candidateId: string;
  rect: RectSnapshot;
  viewport: ViewportSnapshot;
  forPresentation: boolean;
  acquisitionStore: AcquisitionHandoffStore;
  sessionStillActive?(): Promise<boolean>;
}): Promise<AcquisitionOutcome> {
  const known = options.session.candidates[options.candidateId];
  if (!known) return failed(options.candidateId, 'CANDIDATE_NOT_FOUND', 'Candidate is not registered in the active PageSession.');

  const active = await browser.tabs.query({ active: true, windowId: options.session.windowId });
  if (active[0]?.id !== options.session.tabId) {
    return failed(options.candidateId, 'CAPTURE_AWAITING_FOCUS', 'Return to the manga tab before screenshot capture.');
  }

  if (Date.now() - lastCaptureAt < SCREENSHOT_MIN_START_INTERVAL_MS) {
    return failed(options.candidateId, 'CAPTURE_THROTTLED', 'Screenshot capture is limited to two calls per second.');
  }

  try {
    // Reserve the slot before the async browser call so concurrent requests cannot exceed the API limit.
    lastCaptureAt = Date.now();
    const dataUrl = await browser.tabs.captureVisibleTab(options.session.windowId, { format: 'png' });
    const fullBlob = await (await fetch(dataUrl)).blob();
    if (fullBlob.size > MAX_SOURCE_BYTES) {
      return failed(options.candidateId, 'SOURCE_TOO_LARGE', 'Captured viewport exceeds the V1 source-size limit.');
    }
    const bitmap = await createImageBitmap(fullBlob);
    try {
      const crop = computeScreenshotCrop(options.rect, options.viewport, { width: bitmap.width, height: bitmap.height });
      if (!crop) return failed(options.candidateId, 'CAPTURE_EMPTY_INTERSECTION', 'Candidate is not visible in the captured viewport.');

      const canvas = new OffscreenCanvas(crop.source.width, crop.source.height);
      const ctx = canvas.getContext('2d');
      if (!ctx) return failed(options.candidateId, 'CAPTURE_FAILED', 'OffscreenCanvas 2D context is unavailable.');
      ctx.drawImage(
        bitmap,
        crop.source.x,
        crop.source.y,
        crop.source.width,
        crop.source.height,
        0,
        0,
        crop.source.width,
        crop.source.height
      );
      const cropped = await canvas.convertToBlob({ type: 'image/png' });
      const validated = await validateImageBlob(cropped);
      const segmentRect = {
        x: crop.targetVisibleRect.x - options.rect.x,
        y: crop.targetVisibleRect.y - options.rect.y,
        width: crop.targetVisibleRect.width,
        height: crop.targetVisibleRect.height
      };
      if (options.sessionStillActive && !(await options.sessionStillActive())) {
        return failed(options.candidateId, 'STALE_SESSION', 'PageSession changed before screenshot acquisition completed.');
      }

      const stored: AcquiredImage & { blob: Blob } = {
        candidateId: options.candidateId,
        method: 'viewport-capture',
        blob: validated.blob,
        mimeType: validated.mimeType,
        pixelWidth: validated.width,
        pixelHeight: validated.height,
        ...(known.sourceUrl ? { sourceUrl: known.sourceUrl } : {}),
        authority: 'visual-capture',
        capture: { mode: 'viewport-segment', rect: segmentRect }
      };
      const acquisitionId = options.acquisitionStore.put(options.session.sessionId, stored);
      return {
        ok: true,
        image: {
          candidateId: stored.candidateId,
          method: stored.method,
          acquisitionId,
          ...(options.forPresentation ? { blob: stored.blob } : {}),
          mimeType: stored.mimeType,
          pixelWidth: validated.width,
          pixelHeight: validated.height,
          ...(known.sourceUrl ? { sourceUrl: known.sourceUrl } : {}),
          authority: 'visual-capture',
          capture: { mode: 'viewport-segment', rect: segmentRect }
        }
      };
    } finally {
      bitmap.close();
    }
  } catch (error) {
    return failed(
      options.candidateId,
      error instanceof AppError ? error.code : 'CAPTURE_FAILED',
      error instanceof Error ? error.message : 'Screenshot capture failed.'
    );
  }
}

export async function containsExactOrigin(origin: string): Promise<boolean> {
  const pattern = exactOriginPattern(origin);
  if (!pattern) return false;
  return await browser.permissions.contains({ origins: [pattern] });
}

function canonicalUrl(value: string): string | null {
  try {
    return new URL(value).href;
  } catch {
    return null;
  }
}

function failed(candidateId: string, code: string, message: string): AcquisitionOutcome {
  return { ok: false, failure: { reason: 'failed', candidateId, code, message } };
}

function permissionNeeded(candidateId: string, origin: string): AcquisitionOutcome {
  return { ok: false, failure: { reason: 'permission-needed', candidateId, origin } };
}

