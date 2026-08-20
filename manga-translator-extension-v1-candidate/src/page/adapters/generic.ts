import type { SiteAdapter } from './adapter.js';

export const genericAdapter: SiteAdapter = {
  id: 'generic',
  matches: () => true,
  findReaderRoot: (document) => document.documentElement,
  collectCandidates: (root) => Array.from(root.querySelectorAll('img, canvas, iframe')),
  getSourceHint(element) {
    return (
      element.getAttribute('data-page') ??
      element.getAttribute('data-page-index') ??
      element.getAttribute('data-index') ??
      element.getAttribute('aria-posinset')
    );
  }
};
