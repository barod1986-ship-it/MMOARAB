import { ImageSwapPresenter } from './image-swap.js';
import { OverlayPresenter } from './overlay.js';
import type { AcquiredImage } from '../types.js';

type ResultPresentationOptions = {
  autoShow: boolean;
  showCompactControls: boolean;
  locale: 'en' | 'ar';
};

type PresentationRecord = {
  blob: Blob;
  target: Element;
  capture?: AcquiredImage['capture'];
  applied: boolean;
  control?: ResultToggleControl;
};

export class PresentationManager {
  readonly #swaps = new ImageSwapPresenter();
  readonly #overlays = new OverlayPresenter();
  readonly #records = new Map<string, PresentationRecord>();

  async showPlaceholder(
    candidateId: string,
    target: Element,
    blob: Blob,
    capture?: AcquiredImage['capture']
  ): Promise<void> {
    this.showOriginal(candidateId);
    const record: PresentationRecord = { blob, target, ...(capture ? { capture } : {}), applied: false };
    this.#records.set(candidateId, record);
    try {
      await this.#apply(candidateId, record);
      record.applied = true;
    } catch (error) {
      this.#records.delete(candidateId);
      throw error;
    }
  }

  async storeResult(
    candidateId: string,
    target: Element,
    blob: Blob,
    capture: AcquiredImage['capture'] | undefined,
    options: ResultPresentationOptions
  ): Promise<'applied' | 'stored'> {
    this.showOriginal(candidateId);
    const record: PresentationRecord = { blob, target, ...(capture ? { capture } : {}), applied: false };
    this.#records.set(candidateId, record);
    try {
      if (options.autoShow) {
        await this.#apply(candidateId, record);
        record.applied = true;
      }
      if (options.showCompactControls) {
        record.control = new ResultToggleControl(target, options.locale, record.applied, async () => {
          const current = this.#records.get(candidateId);
          if (!current) return false;
          if (current.applied) {
            this.#hideVisual(candidateId, current);
            return false;
          }
          await this.#apply(candidateId, current);
          current.applied = true;
          return true;
        });
      }
      return record.applied ? 'applied' : 'stored';
    } catch (error) {
      record.control?.remove();
      this.#records.delete(candidateId);
      this.#swaps.restore(candidateId);
      this.#overlays.remove(candidateId);
      throw error;
    }
  }

  async syncTarget(candidateId: string, target: Element): Promise<'none' | 'stored' | 'same' | 'reattached' | 'failed'> {
    const record = this.#records.get(candidateId);
    if (!record) return 'none';
    if (record.target === target) {
      record.control?.setTarget(target);
      return record.applied ? 'same' : 'stored';
    }

    this.#swaps.restore(candidateId);
    this.#overlays.remove(candidateId);
    record.target = target;
    record.control?.setTarget(target);
    if (!record.applied) return 'stored';
    record.applied = false;
    try {
      await this.#apply(candidateId, record);
      record.applied = true;
      record.control?.setApplied(true);
      return 'reattached';
    } catch {
      record.control?.remove();
      this.#records.delete(candidateId);
      return 'failed';
    }
  }

  /** Discards the translated presentation record and restores the site-owned original. */
  showOriginal(candidateId: string): boolean {
    const swap = this.#swaps.restore(candidateId);
    const overlay = this.#overlays.remove(candidateId);
    const record = this.#records.get(candidateId);
    record?.control?.remove();
    const hadRecord = this.#records.delete(candidateId);
    return swap || overlay || hadRecord;
  }

  restoreAll(): string[] {
    const ids = new Set<string>(this.#records.keys());
    for (const record of this.#records.values()) record.control?.remove();
    for (const id of this.#swaps.restoreAll()) ids.add(id);
    for (const id of this.#overlays.removeAll()) ids.add(id);
    this.#records.clear();
    return [...ids];
  }

  async #apply(candidateId: string, record: PresentationRecord): Promise<void> {
    if (record.capture?.mode === 'viewport-segment') {
      await this.#overlays.show(candidateId, record.target, record.blob, record.capture.rect);
      return;
    }
    if (record.target instanceof HTMLImageElement) {
      try {
        await this.#swaps.show(candidateId, record.target, record.blob, (kind, image) => {
          void this.#handleSiteRewrite(candidateId, kind, image);
        });
        return;
      } catch {
        // Reader rejected blob/source swap. Use extension-owned overlay instead.
      }
    }
    await this.#overlays.show(candidateId, record.target, record.blob);
  }

  #hideVisual(candidateId: string, record: PresentationRecord): void {
    this.#swaps.restore(candidateId);
    this.#overlays.remove(candidateId);
    record.applied = false;
    record.control?.setApplied(false);
  }

  async #handleSiteRewrite(candidateId: string, kind: 'same-source' | 'new-source', image: HTMLImageElement): Promise<void> {
    const record = this.#records.get(candidateId);
    if (!record || record.target !== image) return;
    if (kind === 'new-source') {
      this.#swaps.abandonForNewSource(candidateId);
      record.control?.remove();
      this.#records.delete(candidateId);
      return;
    }

    this.#swaps.restore(candidateId);
    try {
      await this.#overlays.show(candidateId, image, record.blob);
      record.applied = true;
      record.control?.setApplied(true);
    } catch {
      record.control?.remove();
      this.#records.delete(candidateId);
    }
  }
}

class ResultToggleControl {
  readonly #host: HTMLDivElement;
  readonly #button: HTMLButtonElement;
  readonly #locale: 'en' | 'ar';
  readonly #toggle: () => Promise<boolean>;
  #target: Element;
  #applied: boolean;
  #raf: number | null = null;

  constructor(target: Element, locale: 'en' | 'ar', applied: boolean, toggle: () => Promise<boolean>) {
    this.#target = target;
    this.#locale = locale;
    this.#applied = applied;
    this.#toggle = toggle;
    this.#host = document.createElement('div');
    this.#host.dataset.mteOwned = 'result-toggle';
    this.#host.style.position = 'absolute';
    this.#host.style.zIndex = '2147483647';
    this.#host.style.pointerEvents = 'auto';
    const shadow = this.#host.attachShadow({ mode: 'closed' });
    const style = document.createElement('style');
    style.textContent = `button{font:600 12px/1.2 system-ui,sans-serif;min-height:28px;padding:5px 8px;border:1px solid rgba(0,0,0,.28);border-radius:8px;background:Canvas;color:CanvasText;box-shadow:0 2px 8px rgba(0,0,0,.18);cursor:pointer}button:focus-visible{outline:3px solid Highlight;outline-offset:2px}`;
    this.#button = document.createElement('button');
    this.#button.type = 'button';
    this.#button.addEventListener('click', () => { void this.#onClick(); });
    shadow.append(style, this.#button);
    document.documentElement.append(this.#host);
    window.addEventListener('scroll', this.#schedulePosition, { passive: true });
    window.addEventListener('resize', this.#schedulePosition, { passive: true });
    this.#updateLabel();
    this.#position();
  }

  setTarget(target: Element): void { this.#target = target; this.#schedulePosition(); }
  setApplied(applied: boolean): void { this.#applied = applied; this.#updateLabel(); this.#schedulePosition(); }

  remove(): void {
    window.removeEventListener('scroll', this.#schedulePosition);
    window.removeEventListener('resize', this.#schedulePosition);
    if (this.#raf !== null) cancelAnimationFrame(this.#raf);
    this.#host.remove();
  }

  readonly #schedulePosition = () => {
    if (this.#raf !== null) return;
    this.#raf = requestAnimationFrame(() => { this.#raf = null; this.#position(); });
  };

  async #onClick(): Promise<void> {
    this.#button.disabled = true;
    try { this.setApplied(await this.#toggle()); } finally { this.#button.disabled = false; }
  }

  #updateLabel(): void {
    const labels = this.#locale === 'ar'
      ? { original: 'إظهار الأصل', translated: 'إظهار الترجمة' }
      : { original: 'Show original', translated: 'Show translation' };
    const label = this.#applied ? labels.original : labels.translated;
    this.#button.textContent = this.#applied ? (this.#locale === 'ar' ? 'الأصل' : 'Original') : (this.#locale === 'ar' ? 'الترجمة' : 'Translation');
    this.#button.title = label;
    this.#button.setAttribute('aria-label', label);
  }

  #position(): void {
    if (!this.#target.isConnected) { this.#host.hidden = true; return; }
    const rect = this.#target.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) { this.#host.hidden = true; return; }
    this.#host.hidden = false;
    const left = Math.max(window.scrollX + 4, window.scrollX + rect.right - 112);
    const top = Math.max(window.scrollY + 4, window.scrollY + rect.top + 6);
    this.#host.style.left = `${left}px`;
    this.#host.style.top = `${top}px`;
  }
}
