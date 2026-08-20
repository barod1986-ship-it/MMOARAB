export interface SiteAdapter {
  id: string;
  matches(url: URL): boolean;
  findReaderRoot(document: Document): Element | null;
  collectCandidates(root: Element): Element[];
  getSourceHint?(element: Element): string | null;
  getOrderHint?(element: Element): number | null;
  classifyMode?(): 'paged-manga' | 'long-webtoon' | 'canvas-reader';
}
