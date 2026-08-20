import { AppError } from '../../core/errors.js';

export type ImageSwapSnapshot = {
  src: string | null;
  srcset: string | null;
  sizes: string | null;
  originalCurrentSrc: string;
  pictureSources: Array<{
    element: HTMLSourceElement;
    srcset: string | null;
    sizes: string | null;
  }>;
};

type ActiveSwap = {
  image: HTMLImageElement;
  objectUrl: string;
  snapshot: ImageSwapSnapshot;
  observer: MutationObserver;
  onSiteRewrite: (kind: 'same-source' | 'new-source', image: HTMLImageElement) => void;
};

export class ImageSwapPresenter {
  readonly #active = new Map<string, ActiveSwap>();

  async show(
    candidateId: string,
    image: HTMLImageElement,
    blob: Blob,
    onSiteRewrite: (kind: 'same-source' | 'new-source', image: HTMLImageElement) => void
  ): Promise<void> {
    this.restore(candidateId);
    const snapshot = captureImageState(image);
    const objectUrl = URL.createObjectURL(blob);
    const sources = pictureSources(image);

    image.dataset.mtePresentedFor = candidateId;
    image.src = objectUrl;
    image.srcset = objectUrl;
    for (const source of sources) source.srcset = objectUrl;

    try {
      await waitForImage(image);
      if (!image.isConnected || image.currentSrc !== objectUrl) {
        throw new AppError('PRESENTATION_FAILED', 'Reader replaced or reverted the translated image source.');
      }

      const observer = new MutationObserver(() => {
        queueMicrotask(() => this.#checkForSiteRewrite(candidateId));
      });
      const observationRoot = image.parentElement instanceof HTMLPictureElement ? image.parentElement : image;
      observer.observe(observationRoot, {
        attributes: true,
        subtree: observationRoot !== image,
        attributeFilter: ['src', 'srcset', 'sizes']
      });
      this.#active.set(candidateId, { image, objectUrl, snapshot, observer, onSiteRewrite });
    } catch (error) {
      restoreImageState(image, snapshot);
      removePresentedMarker(image, candidateId);
      URL.revokeObjectURL(objectUrl);
      throw error;
    }
  }

  isTarget(candidateId: string, target: Element): boolean {
    return this.#active.get(candidateId)?.image === target;
  }

  restore(candidateId: string): boolean {
    const active = this.#active.get(candidateId);
    if (!active) return false;
    active.observer.disconnect();
    restoreImageState(active.image, active.snapshot);
    removePresentedMarker(active.image, candidateId);
    URL.revokeObjectURL(active.objectUrl);
    this.#active.delete(candidateId);
    return true;
  }

  abandonForNewSource(candidateId: string): boolean {
    const active = this.#active.get(candidateId);
    if (!active) return false;
    active.observer.disconnect();
    clearOnlyExtensionSources(active.image, active.objectUrl);
    removePresentedMarker(active.image, candidateId);
    URL.revokeObjectURL(active.objectUrl);
    this.#active.delete(candidateId);
    return true;
  }

  restoreAll(): string[] {
    const restored: string[] = [];
    for (const id of [...this.#active.keys()]) {
      if (this.restore(id)) restored.push(id);
    }
    return restored;
  }

  #checkForSiteRewrite(candidateId: string): void {
    const active = this.#active.get(candidateId);
    if (!active) return;
    if (allExtensionSourcesStillApplied(active)) return;

    const sameSource = siteRestoredOriginal(active);
    active.onSiteRewrite(sameSource ? 'same-source' : 'new-source', active.image);
  }
}

function captureImageState(image: HTMLImageElement): ImageSwapSnapshot {
  return {
    src: image.getAttribute('src'),
    srcset: image.getAttribute('srcset'),
    sizes: image.getAttribute('sizes'),
    originalCurrentSrc: image.currentSrc,
    pictureSources: pictureSources(image).map((element) => ({
      element,
      srcset: element.getAttribute('srcset'),
      sizes: element.getAttribute('sizes')
    }))
  };
}

function allExtensionSourcesStillApplied(active: ActiveSwap): boolean {
  if (active.image.getAttribute('src') !== active.objectUrl) return false;
  if (active.image.getAttribute('srcset') !== active.objectUrl) return false;
  for (const source of active.snapshot.pictureSources) {
    if (source.element.isConnected && source.element.getAttribute('srcset') !== active.objectUrl) return false;
  }
  return true;
}

function siteRestoredOriginal(active: ActiveSwap): boolean {
  const src = active.image.getAttribute('src');
  const srcset = active.image.getAttribute('srcset');
  if (src !== active.objectUrl && src === active.snapshot.src) return true;
  if (srcset !== active.objectUrl && srcset === active.snapshot.srcset) return true;
  for (const source of active.snapshot.pictureSources) {
    const current = source.element.getAttribute('srcset');
    if (current !== active.objectUrl && current === source.srcset) return true;
  }
  const currentSrc = active.image.currentSrc;
  return Boolean(active.snapshot.originalCurrentSrc && currentSrc === active.snapshot.originalCurrentSrc);
}

function clearOnlyExtensionSources(image: HTMLImageElement, objectUrl: string): void {
  if (image.getAttribute('src') === objectUrl) image.removeAttribute('src');
  if (image.getAttribute('srcset') === objectUrl) image.removeAttribute('srcset');
  for (const source of pictureSources(image)) {
    if (source.getAttribute('srcset') === objectUrl) source.removeAttribute('srcset');
  }
}

function restoreImageState(image: HTMLImageElement, snapshot: ImageSwapSnapshot): void {
  restoreAttribute(image, 'src', snapshot.src);
  restoreAttribute(image, 'srcset', snapshot.srcset);
  restoreAttribute(image, 'sizes', snapshot.sizes);
  for (const source of snapshot.pictureSources) {
    restoreAttribute(source.element, 'srcset', source.srcset);
    restoreAttribute(source.element, 'sizes', source.sizes);
  }
}

function pictureSources(image: HTMLImageElement): HTMLSourceElement[] {
  const parent = image.parentElement;
  return parent instanceof HTMLPictureElement ? Array.from(parent.querySelectorAll('source')) : [];
}

function restoreAttribute(element: Element, name: string, value: string | null): void {
  if (value === null) element.removeAttribute(name);
  else element.setAttribute(name, value);
}

function removePresentedMarker(image: HTMLImageElement, candidateId: string): void {
  if (image.dataset.mtePresentedFor === candidateId) delete image.dataset.mtePresentedFor;
}

async function waitForImage(image: HTMLImageElement): Promise<void> {
  if (image.complete && image.naturalWidth > 0) {
    try {
      await image.decode();
    } catch {
      // load state below is still authoritative enough for presentation fallback selection.
    }
    return;
  }
  await new Promise<void>((resolve, reject) => {
    const onLoad = (): void => {
      cleanup();
      resolve();
    };
    const onError = (): void => {
      cleanup();
      reject(new AppError('PRESENTATION_FAILED', 'Translated object URL failed to load.'));
    };
    const cleanup = (): void => {
      image.removeEventListener('load', onLoad);
      image.removeEventListener('error', onError);
    };
    image.addEventListener('load', onLoad, { once: true });
    image.addEventListener('error', onError, { once: true });
  });
}
