import { EXTENSION_DOM_PREFIX } from '../shared/constants.js';
import { newCandidateId } from '../shared/ids.js';
import { buildSourceKey, getSourceOrigin, resolveImageSource, sourceFamily } from './source-resolver.js';
import { applyGroupBoost, scoreCandidate, type GroupMember } from './scoring.js';
import type { CandidateSummary, PageImageCandidate, PageSnapshot, RectSnapshot } from './types.js';
import type { SiteAdapter } from './adapters/adapter.js';

const SEMANTIC_UI_SELECTOR = 'nav,header,footer,aside,[role="navigation"],[role="banner"],[role="contentinfo"]';

export class CandidateRegistry {
  readonly #sessionId: string;
  readonly #adapter: SiteAdapter;
  readonly #records = new Map<string, PageImageCandidate>();
  readonly #elements = new Map<string, Element>();
  readonly #elementIds = new WeakMap<Element, string>();
  readonly #sourceIds = new Map<string, string>();
  readonly #parentIds = new WeakMap<Element, string>();
  #parentSequence = 0;

  constructor(sessionId: string, adapter: SiteAdapter) {
    this.#sessionId = sessionId;
    this.#adapter = adapter;
  }

  scan(root: Element): PageSnapshot {
    const seen = new Set<string>();
    const elements = this.#adapter.collectCandidates(root);
    const groups: GroupMember[] = [];

    for (let index = 0; index < elements.length; index += 1) {
      const element = elements[index];
      if (!element) continue;
      const candidate = this.#upsert(element, index);
      if (!candidate) continue;
      seen.add(candidate.candidateId);
      if (candidate.kind === 'img') groups.push(this.#groupMember(candidate, element));
    }

    const boosted = applyGroupBoost(groups);
    for (const [id, confidence] of boosted) {
      const record = this.#records.get(id);
      if (record) record.confidence = confidence;
    }

    for (const [id, record] of this.#records) {
      if (!seen.has(id)) record.state = 'stale';
    }

    return this.snapshot();
  }

  snapshot(): PageSnapshot {
    return {
      sessionId: this.#sessionId,
      pageUrl: location.href,
      candidates: [...this.#records.values()]
        .filter((candidate) => candidate.state !== 'stale')
        .sort((a, b) => (a.orderHint ?? Number.MAX_SAFE_INTEGER) - (b.orderHint ?? Number.MAX_SAFE_INTEGER))
        .map(cloneCandidate),
      updatedAt: Date.now()
    };
  }

  get(candidateId: string): PageImageCandidate | undefined {
    return this.#records.get(candidateId);
  }

  getElement(candidateId: string): Element | undefined {
    return this.#elements.get(candidateId);
  }

  updateState(candidateId: string, state: PageImageCandidate['state']): void {
    const record = this.#records.get(candidateId);
    if (record) record.state = state;
  }

  updateNearViewport(candidateId: string, nearViewport: boolean): void {
    const record = this.#records.get(candidateId);
    if (record) record.nearViewport = nearViewport;
  }

  refreshGeometry(candidateId: string): RectSnapshot | null {
    const element = this.#elements.get(candidateId);
    const record = this.#records.get(candidateId);
    if (!element || !record || !element.isConnected) return null;
    const rect = rectSnapshot(element.getBoundingClientRect());
    record.rect = rect;
    if (element instanceof HTMLImageElement) {
      record.naturalWidth = element.naturalWidth;
      record.naturalHeight = element.naturalHeight;
    } else if (element instanceof HTMLCanvasElement) {
      record.naturalWidth = element.width;
      record.naturalHeight = element.height;
    }
    return rect;
  }

  clear(): void {
    for (const element of this.#elements.values()) element.removeAttribute('data-mte-candidate-id');
    this.#records.clear();
    this.#elements.clear();
    this.#sourceIds.clear();
  }

  #upsert(element: Element, orderHint: number): PageImageCandidate | null {
    if (element.closest(`[data-${EXTENSION_DOM_PREFIX}owned="true"]`)) return null;
    if (element instanceof HTMLImageElement) return this.#upsertImage(element, orderHint);
    if (element instanceof HTMLCanvasElement) return this.#upsertCanvas(element, orderHint);
    if (element instanceof HTMLIFrameElement) return this.#upsertViewportRegion(element, orderHint);
    return null;
  }

  #upsertImage(img: HTMLImageElement, orderHint: number): PageImageCandidate | null {
    const presentedFor = img.dataset.mtePresentedFor;
    if (presentedFor) {
      const presented = this.#records.get(presentedFor);
      if (presented && this.#elements.get(presentedFor) === img) {
        presented.rect = rectSnapshot(img.getBoundingClientRect());
        presented.orderHint = orderHint;
        presented.state = 'translated';
        return presented;
      }
    }

    const sourceUrl = resolveImageSource(img);
    const hint = this.#adapter.getSourceHint?.(img) ?? null;
    const sourceKey = buildSourceKey(this.#sessionId, 'img', sourceUrl, hint);
    const existingElementId = this.#elementIds.get(img);
    if (existingElementId) {
      const existing = this.#records.get(existingElementId);
      if (existing) {
        if (existing.sourceKey !== sourceKey) {
          this.#rebindSource(existing, sourceKey, sourceUrl);
        }
        this.#refreshImage(existing, img, orderHint);
        return existing;
      }
      this.#elements.delete(existingElementId);
    }

    const reusableId = this.#sourceIds.get(sourceKey);
    if (reusableId) {
      const priorElement = this.#elements.get(reusableId);
      const reusable = this.#records.get(reusableId);
      if (reusable && (!priorElement || !priorElement.isConnected)) {
        this.#elementIds.set(img, reusableId);
        this.#elements.set(reusableId, img);
        reusable.state = imageState(img, sourceUrl);
        this.#refreshImage(reusable, img, orderHint);
        return reusable;
      }
    }

    const candidateId = newCandidateId();
    const rect = rectSnapshot(img.getBoundingClientRect());
    const sourceOrigin = getSourceOrigin(sourceUrl);
    const candidate: PageImageCandidate = {
      candidateId,
      kind: 'img',
      ...(sourceUrl ? { sourceUrl } : {}),
      ...(sourceOrigin ? { sourceOrigin } : {}),
      sourceKey,
      sourceRevision: 1,
      rect,
      naturalWidth: img.naturalWidth,
      naturalHeight: img.naturalHeight,
      orderHint,
      confidence: this.#score(img, rect, sourceUrl),
      adapterId: this.#adapter.id,
      state: imageState(img, sourceUrl)
    };
    this.#records.set(candidateId, candidate);
    this.#elements.set(candidateId, img);
    this.#elementIds.set(img, candidateId);
    this.#sourceIds.set(sourceKey, candidateId);
    return candidate;
  }

  #upsertCanvas(canvas: HTMLCanvasElement, orderHint: number): PageImageCandidate {
    const hint = this.#adapter.getSourceHint?.(canvas) ?? `canvas-${orderHint}`;
    const sourceKey = buildSourceKey(this.#sessionId, 'canvas', null, hint);
    const existingId = this.#elementIds.get(canvas);
    if (existingId) {
      const existing = this.#records.get(existingId);
      if (existing) {
        this.#refreshCanvas(existing, canvas, orderHint);
        return existing;
      }
    }

    const candidateId = newCandidateId();
    const rect = rectSnapshot(canvas.getBoundingClientRect());
    const candidate: PageImageCandidate = {
      candidateId,
      kind: 'canvas',
      sourceKey,
      sourceRevision: 1,
      rect,
      naturalWidth: canvas.width,
      naturalHeight: canvas.height,
      orderHint,
      confidence: this.#score(canvas, rect, null),
      adapterId: this.#adapter.id,
      state: canvas.width > 0 && canvas.height > 0 ? 'ready' : 'waiting-load'
    };
    this.#records.set(candidateId, candidate);
    this.#elements.set(candidateId, canvas);
    this.#elementIds.set(canvas, candidateId);
    this.#sourceIds.set(sourceKey, candidateId);
    return candidate;
  }


  #upsertViewportRegion(iframe: HTMLIFrameElement, orderHint: number): PageImageCandidate {
    const sourceUrl = resolveFrameSource(iframe);
    const hint = this.#adapter.getSourceHint?.(iframe) ?? `iframe-${orderHint}`;
    const sourceKey = buildSourceKey(this.#sessionId, 'viewport-region', sourceUrl, hint);
    const existingId = this.#elementIds.get(iframe);
    if (existingId) {
      const existing = this.#records.get(existingId);
      if (existing) {
        if (existing.sourceKey !== sourceKey) {
          this.#rebindSource(existing, sourceKey, sourceUrl);
        }
        existing.rect = rectSnapshot(iframe.getBoundingClientRect());
        existing.orderHint = orderHint;
        existing.confidence = this.#score(iframe, existing.rect, sourceUrl);
        existing.state = existing.rect.width > 0 && existing.rect.height > 0 ? 'ready' : 'waiting-load';
        return existing;
      }
      this.#elements.delete(existingId);
    }

    const reusableId = this.#sourceIds.get(sourceKey);
    if (reusableId) {
      const priorElement = this.#elements.get(reusableId);
      const reusable = this.#records.get(reusableId);
      if (reusable && (!priorElement || !priorElement.isConnected)) {
        this.#elementIds.set(iframe, reusableId);
        this.#elements.set(reusableId, iframe);
        reusable.rect = rectSnapshot(iframe.getBoundingClientRect());
        reusable.orderHint = orderHint;
        reusable.confidence = this.#score(iframe, reusable.rect, sourceUrl);
        reusable.state = reusable.rect.width > 0 && reusable.rect.height > 0 ? 'ready' : 'waiting-load';
        return reusable;
      }
    }

    const candidateId = newCandidateId();
    const rect = rectSnapshot(iframe.getBoundingClientRect());
    const sourceOrigin = getSourceOrigin(sourceUrl);
    const candidate: PageImageCandidate = {
      candidateId,
      kind: 'viewport-region',
      ...(sourceUrl ? { sourceUrl } : {}),
      ...(sourceOrigin ? { sourceOrigin } : {}),
      sourceKey,
      sourceRevision: 1,
      rect,
      orderHint,
      confidence: this.#score(iframe, rect, sourceUrl),
      adapterId: this.#adapter.id,
      state: rect.width > 0 && rect.height > 0 ? 'ready' : 'waiting-load'
    };
    this.#records.set(candidateId, candidate);
    this.#elements.set(candidateId, iframe);
    this.#elementIds.set(iframe, candidateId);
    this.#sourceIds.set(sourceKey, candidateId);
    return candidate;
  }

  #refreshImage(candidate: PageImageCandidate, img: HTMLImageElement, orderHint: number): void {
    const sourceUrl = resolveImageSource(img);
    candidate.rect = rectSnapshot(img.getBoundingClientRect());
    candidate.naturalWidth = img.naturalWidth;
    candidate.naturalHeight = img.naturalHeight;
    candidate.orderHint = orderHint;
    candidate.confidence = this.#score(img, candidate.rect, sourceUrl);
    candidate.state = imageState(img, sourceUrl);
    if (sourceUrl) candidate.sourceUrl = sourceUrl;
    else delete candidate.sourceUrl;
    const origin = getSourceOrigin(sourceUrl);
    if (origin) candidate.sourceOrigin = origin;
    else delete candidate.sourceOrigin;
  }

  #rebindSource(candidate: PageImageCandidate, nextSourceKey: string, nextSourceUrl: string | null): void {
    if (this.#sourceIds.get(candidate.sourceKey) === candidate.candidateId) {
      this.#sourceIds.delete(candidate.sourceKey);
    }
    candidate.sourceKey = nextSourceKey;
    candidate.sourceRevision += 1;
    if (nextSourceUrl) candidate.sourceUrl = nextSourceUrl;
    else delete candidate.sourceUrl;
    const origin = getSourceOrigin(nextSourceUrl);
    if (origin) candidate.sourceOrigin = origin;
    else delete candidate.sourceOrigin;
    candidate.state = 'ready';
    this.#sourceIds.set(nextSourceKey, candidate.candidateId);
  }

  #refreshCanvas(candidate: PageImageCandidate, canvas: HTMLCanvasElement, orderHint: number): void {
    candidate.rect = rectSnapshot(canvas.getBoundingClientRect());
    candidate.naturalWidth = canvas.width;
    candidate.naturalHeight = canvas.height;
    candidate.orderHint = orderHint;
    candidate.confidence = this.#score(canvas, candidate.rect, null);
    candidate.state = canvas.width > 0 && canvas.height > 0 ? 'ready' : 'waiting-load';
  }

  #score(element: HTMLElement, rect: RectSnapshot, sourceUrl: string | null): number {
    const style = getComputedStyle(element);
    const hidden = style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0;
    const naturalWidth = element instanceof HTMLImageElement ? element.naturalWidth : element instanceof HTMLCanvasElement ? element.width : 0;
    const naturalHeight = element instanceof HTMLImageElement ? element.naturalHeight : element instanceof HTMLCanvasElement ? element.height : 0;
    return scoreCandidate({
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
      rect,
      naturalWidth,
      naturalHeight,
      visible:
        rect.y + rect.height > 0 &&
        rect.x + rect.width > 0 &&
        rect.x < window.innerWidth &&
        rect.y < window.innerHeight,
      hidden,
      insideChromeUi: Boolean(element.closest(SEMANTIC_UI_SELECTOR)),
      insideSemanticUi: Boolean(element.closest('[role="toolbar"],[role="menu"],[role="dialog"]')),
      likelyTrackingPixel: naturalWidth <= 2 && naturalHeight <= 2,
      extensionOwned: Boolean(element.closest(`[data-${EXTENSION_DOM_PREFIX}owned="true"]`)),
      ...(sourceUrl ? { sourceUrl } : {})
    });
  }

  #groupMember(candidate: PageImageCandidate, element: Element): GroupMember {
    const parent = element.parentElement ?? document.documentElement;
    let parentKey = this.#parentIds.get(parent);
    if (!parentKey) {
      this.#parentSequence += 1;
      parentKey = `group-${this.#parentSequence}`;
      this.#parentIds.set(parent, parentKey);
    }
    candidate.groupId = parentKey;
    return {
      id: candidate.candidateId,
      parentKey,
      sourceFamily: sourceFamily(candidate.sourceUrl ?? null),
      centerX: candidate.rect.x + candidate.rect.width / 2,
      width: candidate.rect.width,
      top: candidate.rect.y,
      bottom: candidate.rect.y + candidate.rect.height,
      baseScore: candidate.confidence
    };
  }
}


function resolveFrameSource(iframe: HTMLIFrameElement): string | null {
  const raw = iframe.getAttribute('src')?.trim();
  if (!raw || raw === 'about:blank') return null;
  try {
    const url = new URL(raw, document.baseURI);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null;
  } catch {
    return null;
  }
}

function imageState(img: HTMLImageElement, sourceUrl: string | null): PageImageCandidate['state'] {
  if (!sourceUrl) return 'waiting-load';
  return img.complete && img.naturalWidth > 0 ? 'ready' : 'waiting-load';
}

function rectSnapshot(rect: DOMRect | DOMRectReadOnly): RectSnapshot {
  return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
}

function cloneCandidate(candidate: PageImageCandidate): CandidateSummary {
  const rect = candidate.rect;
  const visible = rect.y + rect.height > 0 && rect.x + rect.width > 0 && rect.x < window.innerWidth && rect.y < window.innerHeight;
  const visibility = visible ? 'visible' : candidate.nearViewport ? 'near' : 'far';
  return {
    ...candidate,
    visibility,
    rect: { ...candidate.rect }
  };
}
