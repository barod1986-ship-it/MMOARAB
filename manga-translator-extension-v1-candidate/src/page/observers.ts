import {
  INTERSECTION_ROOT_MARGIN,
  INTERSECTION_THRESHOLD,
  MUTATION_DEBOUNCE_MS,
  RECONCILIATION_INTERVAL_MS
} from '../shared/constants.js';
import type { CandidateRegistry } from './detector.js';
import type { PageSnapshot } from './types.js';

const MUTATION_ATTRIBUTE_FILTER = ['src', 'srcset', 'sizes', 'loading', 'data-src', 'data-lazy-src', 'data-original', 'data-url'] as const;

export class PageObservers {
  readonly #registry: CandidateRegistry;
  readonly #root: Element;
  readonly #onSnapshot: (snapshot: PageSnapshot) => void;
  readonly #onUrlChanged: (nextUrl: string) => void;
  readonly #mutation: MutationObserver;
  readonly #intersection: IntersectionObserver;
  readonly #loadBound = new WeakSet<Element>();
  readonly #loadHandlers = new Map<HTMLImageElement, () => void>();
  #reconcileTimer: number | null = null;
  #debounceTimer: number | null = null;
  #lastUrl = location.href;
  #disposed = false;

  constructor(options: {
    registry: CandidateRegistry;
    root: Element;
    onSnapshot(snapshot: PageSnapshot): void;
    onUrlChanged(nextUrl: string): void;
  }) {
    this.#registry = options.registry;
    this.#root = options.root;
    this.#onSnapshot = options.onSnapshot;
    this.#onUrlChanged = options.onUrlChanged;
    this.#mutation = new MutationObserver(() => this.#scheduleScan());
    this.#intersection = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const candidateId = entry.target.getAttribute('data-mte-candidate-id');
          if (candidateId) this.#registry.updateNearViewport(candidateId, entry.isIntersecting);
        }
        this.#onSnapshot(this.#registry.snapshot());
      },
      { root: null, rootMargin: INTERSECTION_ROOT_MARGIN, threshold: INTERSECTION_THRESHOLD }
    );
  }

  start(): PageSnapshot {
    this.#mutation.observe(this.#root, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: [...MUTATION_ATTRIBUTE_FILTER]
    });
    window.addEventListener('popstate', this.#handleNavigation);
    window.addEventListener('hashchange', this.#handleNavigation);
    window.addEventListener('pageshow', this.#handleNavigation);
    this.#reconcileTimer = window.setInterval(() => this.reconcile(), RECONCILIATION_INTERVAL_MS);
    return this.scanNow();
  }

  scanNow(): PageSnapshot {
    if (this.#disposed) return this.#registry.snapshot();
    this.#checkUrl();
    const snapshot = this.#registry.scan(this.#root);
    this.#syncObservedElements(snapshot);
    this.#bindLoadEvents(snapshot);
    this.#onSnapshot(snapshot);
    return snapshot;
  }

  reconcile(): void {
    if (this.#disposed) return;
    this.#checkUrl();
    if (this.#disposed) return;
    this.scanNow();
  }

  dispose(): void {
    if (this.#disposed) return;
    this.#disposed = true;
    this.#mutation.disconnect();
    this.#intersection.disconnect();
    if (this.#reconcileTimer !== null) window.clearInterval(this.#reconcileTimer);
    if (this.#debounceTimer !== null) window.clearTimeout(this.#debounceTimer);
    window.removeEventListener('popstate', this.#handleNavigation);
    window.removeEventListener('hashchange', this.#handleNavigation);
    window.removeEventListener('pageshow', this.#handleNavigation);
    for (const [image, refresh] of this.#loadHandlers) {
      image.removeEventListener('load', refresh);
      image.removeEventListener('error', refresh);
    }
    this.#loadHandlers.clear();
  }

  readonly #handleNavigation = (): void => {
    this.#checkUrl();
    if (!this.#disposed) this.#scheduleScan();
  };

  #checkUrl(): void {
    if (location.href === this.#lastUrl) return;
    this.#lastUrl = location.href;
    this.#onUrlChanged(this.#lastUrl);
  }

  #scheduleScan(): void {
    if (this.#disposed) return;
    if (this.#debounceTimer !== null) window.clearTimeout(this.#debounceTimer);
    this.#debounceTimer = window.setTimeout(() => {
      this.#debounceTimer = null;
      this.scanNow();
    }, MUTATION_DEBOUNCE_MS);
  }

  #syncObservedElements(snapshot: PageSnapshot): void {
    this.#intersection.disconnect();
    for (const candidate of snapshot.candidates) {
      const element = this.#registry.getElement(candidate.candidateId);
      if (!element) continue;
      element.setAttribute('data-mte-candidate-id', candidate.candidateId);
      this.#intersection.observe(element);
    }
  }

  #bindLoadEvents(snapshot: PageSnapshot): void {
    for (const candidate of snapshot.candidates) {
      if (candidate.kind !== 'img' || candidate.state !== 'waiting-load') continue;
      const element = this.#registry.getElement(candidate.candidateId);
      if (!(element instanceof HTMLImageElement) || this.#loadBound.has(element)) continue;
      this.#loadBound.add(element);
      const refresh = (): void => {
        element.removeEventListener('load', refresh);
        element.removeEventListener('error', refresh);
        this.#loadHandlers.delete(element);
        this.#scheduleScan();
      };
      this.#loadHandlers.set(element, refresh);
      element.addEventListener('load', refresh, { once: true });
      element.addEventListener('error', refresh, { once: true });
    }
  }
}
