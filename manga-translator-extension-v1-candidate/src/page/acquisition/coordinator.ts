import { serializeError } from '../../core/errors.js';
import type { CandidateRegistry } from '../detector.js';
import type { AcquisitionOutcome, PageImageCandidate } from '../types.js';
import type { PresentationManager } from '../presentation/index.js';
import { acquireCanvas } from './acquire-canvas.js';
import { acquireImageDirect } from './acquire-img.js';
import { acquireViaBackground, hasExactOriginPermission } from './acquire-remote.js';
import { acquireViaScreenshot } from './acquire-screenshot.js';

export class AcquisitionCoordinator {
  readonly #sessionId: string;
  readonly #mainFrameOrigin: string;
  readonly #registry: CandidateRegistry;
  readonly #presentation: PresentationManager;
  readonly #abortController = new AbortController();
  #disposed = false;

  constructor(options: {
    sessionId: string;
    mainFrameOrigin: string;
    registry: CandidateRegistry;
    presentation: PresentationManager;
  }) {
    this.#sessionId = options.sessionId;
    this.#mainFrameOrigin = options.mainFrameOrigin;
    this.#registry = options.registry;
    this.#presentation = options.presentation;
  }

  async acquire(candidateId: string, options: { allowScreenshot: boolean; previewOnPage: boolean }): Promise<AcquisitionOutcome> {
    if (this.#disposed) return stale(candidateId);
    const candidate = this.#registry.get(candidateId);
    const element = this.#registry.getElement(candidateId);
    if (!candidate || !element || candidate.state === 'stale') {
      return failed(candidateId, 'CANDIDATE_NOT_FOUND', 'Candidate is no longer attached to the current page session.');
    }

    this.#registry.refreshGeometry(candidateId);
    let direct: AcquisitionOutcome | null = null;
    try {
      if (candidate.kind === 'img' && element instanceof HTMLImageElement) {
        if (!element.complete || element.naturalWidth <= 0) {
          this.#registry.updateState(candidateId, 'waiting-load');
          return failed(candidateId, 'CANDIDATE_NOT_READY', 'Image is still loading.');
        }
        direct = { ok: true, image: await acquireImageDirect(candidate, element, this.#abortController.signal) };
      } else if (candidate.kind === 'canvas' && element instanceof HTMLCanvasElement) {
        direct = { ok: true, image: await acquireCanvas(candidate, element) };
      }
    } catch {
      // Expected fallback path: fetch/CORS/canvas taint failures continue below.
    }

    if (this.#disposed) return stale(candidateId);
    if (direct?.ok) return await this.#finish(candidate, element, direct, options.previewOnPage);

    if (candidate.kind === 'img' && candidate.sourceUrl) {
      const sourceOrigin = parseHttpOrigin(candidate.sourceUrl);
      if (sourceOrigin) {
        const isMainOrigin = sourceOrigin === this.#mainFrameOrigin;
        let granted = isMainOrigin;
        if (!isMainOrigin) granted = await hasExactOriginPermission(this.#sessionId, candidateId, sourceOrigin);

        if (!granted) {
          this.#registry.updateState(candidateId, 'permission-needed');
          if (!options.allowScreenshot) {
            return { ok: false, failure: { reason: 'permission-needed', origin: sourceOrigin, candidateId } };
          }
          return await this.#capture(candidate, element, options.previewOnPage);
        }

        const remote = await acquireViaBackground({
          sessionId: this.#sessionId,
          candidateId,
          sourceUrl: candidate.sourceUrl,
          forPresentation: options.previewOnPage
        });
        if (this.#disposed) return stale(candidateId);
        if (remote.ok) return await this.#finish(candidate, element, remote, options.previewOnPage);
        if (remote.failure.reason === 'permission-needed' && !options.allowScreenshot) {
          this.#registry.updateState(candidateId, 'permission-needed');
          return remote;
        }
        // A permitted fetch that still fails (anti-hotlink, auth, redirect policy) falls through to screenshot.
      }
    }

    return await this.#capture(candidate, element, options.previewOnPage);
  }

  dispose(): void {
    if (this.#disposed) return;
    this.#disposed = true;
    this.#abortController.abort();
    this.restoreAll();
  }

  showOriginal(candidateId: string): boolean {
    const restored = this.#presentation.showOriginal(candidateId);
    if (restored) this.#registry.updateState(candidateId, 'ready');
    return restored;
  }

  restoreAll(): void {
    for (const candidateId of this.#presentation.restoreAll()) {
      this.#registry.updateState(candidateId, 'ready');
    }
  }

  async #capture(candidate: PageImageCandidate, element: Element, previewOnPage: boolean): Promise<AcquisitionOutcome> {
    for (let attempt = 0; attempt < 2; attempt += 1) {
      if (this.#disposed) return stale(candidate.candidateId);
      const rect = this.#registry.refreshGeometry(candidate.candidateId);
      if (!rect) return failed(candidate.candidateId, 'CANDIDATE_NOT_FOUND', 'Candidate disappeared before screenshot capture.');
      const captured = await acquireViaScreenshot({
        sessionId: this.#sessionId,
        candidateId: candidate.candidateId,
        rect,
        forPresentation: previewOnPage
      });
      if (captured.ok) return await this.#finish(candidate, element, captured, previewOnPage);
      if (captured.failure.reason !== 'failed' || captured.failure.code !== 'CAPTURE_THROTTLED' || attempt > 0) return captured;
      // Re-read geometry/visualViewport after the throttle interval, not before it.
      await sleep(500);
      if (this.#disposed) return stale(candidate.candidateId);
    }
    return failed(candidate.candidateId, 'CAPTURE_FAILED', 'Screenshot capture did not complete.');
  }

  async #finish(
    candidate: PageImageCandidate,
    element: Element,
    outcome: Extract<AcquisitionOutcome, { ok: true }>,
    previewOnPage: boolean
  ): Promise<AcquisitionOutcome> {
    if (this.#disposed) return stale(candidate.candidateId);
    this.#registry.updateState(candidate.candidateId, 'acquired');
    if (previewOnPage && outcome.image.blob) {
      try {
        await this.#presentation.showPlaceholder(candidate.candidateId, element, outcome.image.blob, outcome.image.capture);
        this.#registry.updateState(candidate.candidateId, 'translated');
      } catch (error) {
        const serialized = serializeError(error);
        return failed(candidate.candidateId, serialized.code, serialized.message);
      }
    }
    return outcome;
  }
}

function parseHttpOrigin(sourceUrl: string): string | null {
  try {
    const url = new URL(sourceUrl);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.origin : null;
  } catch {
    return null;
  }
}

function failed(candidateId: string, code: string, message: string): AcquisitionOutcome {
  return { ok: false, failure: { reason: 'failed', candidateId, code, message } };
}

function stale(candidateId: string): AcquisitionOutcome {
  return failed(candidateId, 'STALE_SESSION', 'Acquisition was cancelled because the PageSession changed.');
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}
