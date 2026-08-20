import type { RectSnapshot } from '../types.js';

type OverlayRecord = {
  target: Element;
  image: HTMLImageElement;
  objectUrl: string;
  resizeObserver: ResizeObserver;
  segmentRect?: RectSnapshot;
};

export class OverlayPresenter {
  readonly #active = new Map<string, OverlayRecord>();
  #tracking = false;

  async show(candidateId: string, target: Element, blob: Blob, segmentRect?: RectSnapshot): Promise<void> {
    this.remove(candidateId);
    const objectUrl = URL.createObjectURL(blob);
    const image = document.createElement('img');
    image.dataset.mteOwned = 'true';
    image.dataset.mteOverlayFor = candidateId;
    Object.assign(image.style, {
      position: 'fixed',
      pointerEvents: 'none',
      margin: '0',
      padding: '0',
      border: '0',
      zIndex: '2147483646',
      objectFit: 'fill',
      transformOrigin: 'top left'
    });
    image.src = objectUrl;
    try {
      await waitLoad(image);
      if (!target.isConnected) throw new Error('Overlay target is no longer connected.');
      document.documentElement.append(image);
    } catch (error) {
      URL.revokeObjectURL(objectUrl);
      throw error;
    }

    const resizeObserver = new ResizeObserver(() => this.#position(candidateId));
    resizeObserver.observe(target);
    this.#active.set(candidateId, { target, image, objectUrl, resizeObserver, ...(segmentRect ? { segmentRect } : {}) });
    this.#position(candidateId);
    this.#ensureTracking();
  }

  remove(candidateId: string): boolean {
    const record = this.#active.get(candidateId);
    if (!record) return false;
    record.resizeObserver.disconnect();
    record.image.remove();
    URL.revokeObjectURL(record.objectUrl);
    this.#active.delete(candidateId);
    if (this.#active.size === 0) this.#stopTracking();
    return true;
  }

  removeAll(): string[] {
    const removed: string[] = [];
    for (const id of [...this.#active.keys()]) {
      if (this.remove(id)) removed.push(id);
    }
    return removed;
  }

  #position(candidateId: string): void {
    const record = this.#active.get(candidateId);
    if (!record) return;
    if (!record.target.isConnected) {
      this.remove(candidateId);
      return;
    }
    const rect = record.target.getBoundingClientRect();
    const segment = record.segmentRect;
    const x = rect.x + (segment?.x ?? 0);
    const y = rect.y + (segment?.y ?? 0);
    const width = segment?.width ?? rect.width;
    const height = segment?.height ?? rect.height;
    const style = record.image.style;
    style.left = `${x}px`;
    style.top = `${y}px`;
    style.width = `${Math.max(0, width)}px`;
    style.height = `${Math.max(0, height)}px`;
    style.display = width > 0 && height > 0 ? 'block' : 'none';
  }

  #ensureTracking(): void {
    if (this.#tracking) return;
    this.#tracking = true;
    window.addEventListener('scroll', this.#onLayout, true);
    window.addEventListener('resize', this.#onLayout);
    window.visualViewport?.addEventListener('scroll', this.#onLayout);
    window.visualViewport?.addEventListener('resize', this.#onLayout);
  }

  #stopTracking(): void {
    if (!this.#tracking) return;
    this.#tracking = false;
    window.removeEventListener('scroll', this.#onLayout, true);
    window.removeEventListener('resize', this.#onLayout);
    window.visualViewport?.removeEventListener('scroll', this.#onLayout);
    window.visualViewport?.removeEventListener('resize', this.#onLayout);
  }

  readonly #onLayout = (): void => {
    requestAnimationFrame(() => {
      for (const id of this.#active.keys()) this.#position(id);
    });
  };
}

async function waitLoad(image: HTMLImageElement): Promise<void> {
  if (image.complete && image.naturalWidth > 0) return;
  await new Promise<void>((resolve, reject) => {
    image.addEventListener('load', () => resolve(), { once: true });
    image.addEventListener('error', () => reject(new Error('Overlay image failed to load.')), { once: true });
  });
}
