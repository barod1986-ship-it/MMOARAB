const LAZY_ATTRIBUTES = ['data-src', 'data-lazy-src', 'data-original', 'data-url'] as const;

export type SourceValues = {
  currentSrc?: string | null;
  src?: string | null;
  lazy?: Partial<Record<(typeof LAZY_ATTRIBUTES)[number], string | null>>;
};

export function resolveSourceFromValues(values: SourceValues, baseUrl: string): string | null {
  const raw =
    clean(values.currentSrc) ??
    clean(values.src) ??
    LAZY_ATTRIBUTES.map((name) => clean(values.lazy?.[name])).find((value) => value !== null) ??
    null;
  if (raw === null) return null;
  try {
    return new URL(raw, baseUrl).href;
  } catch {
    return null;
  }
}

export function resolveImageSource(img: HTMLImageElement): string | null {
  const lazy: SourceValues['lazy'] = {};
  for (const name of LAZY_ATTRIBUTES) lazy[name] = img.getAttribute(name);
  return resolveSourceFromValues(
    {
      currentSrc: img.currentSrc,
      src: img.getAttribute('src') ?? img.src,
      lazy
    },
    document.baseURI
  );
}

export function getSourceOrigin(sourceUrl: string | null): string | null {
  if (!sourceUrl) return null;
  try {
    const url = new URL(sourceUrl);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.origin : null;
  } catch {
    return null;
  }
}

export function sourceFamily(sourceUrl: string | null): string {
  if (!sourceUrl) return 'none';
  try {
    const url = new URL(sourceUrl);
    const segments = url.pathname.split('/').filter(Boolean);
    if (segments.length > 0) segments.pop();
    return `${url.origin}/${segments.join('/')}`;
  } catch {
    return 'invalid';
  }
}

export function buildSourceKey(
  sessionId: string,
  kind: 'img' | 'canvas' | 'viewport-region',
  sourceUrl: string | null,
  stableHint?: string | number | null
): string {
  return [sessionId, kind, sourceUrl ?? 'visual', stableHint ?? ''].join('|');
}

function clean(value: string | null | undefined): string | null {
  const trimmed = value?.trim();
  return trimmed ? trimmed : null;
}
