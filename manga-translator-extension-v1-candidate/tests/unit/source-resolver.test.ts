import { expect, it } from 'vitest';
import { buildSourceKey, getSourceOrigin, resolveSourceFromValues, sourceFamily } from '../../src/page/source-resolver.js';

it('currentSrc wins over src and lazy hints', () => {
  expect(
    resolveSourceFromValues(
      { currentSrc: '/large.webp', src: '/small.webp', lazy: { 'data-src': '/lazy.webp' } },
      'https://reader.example/chapter/1'
    )
  ).toBe('https://reader.example/large.webp');
});

it('lazy known attribute is used only when normal sources are empty', () => {
  expect(
    resolveSourceFromValues({ currentSrc: '', src: '', lazy: { 'data-lazy-src': '../img/p17.jpg' } }, 'https://reader.example/c/10/')
  ).toBe('https://reader.example/c/img/p17.jpg');
});

it('source origin ignores blob/data and family groups URL directory', () => {
  expect(getSourceOrigin('blob:https://reader.example/123')).toBeNull();
  expect(sourceFamily('https://cdn.example/ch/10/page-17.webp?x=1')).toBe('https://cdn.example/ch/10');
});

it('source key is session scoped', () => {
  expect(buildSourceKey('a', 'img', 'https://x/y')).not.toBe(buildSourceKey('b', 'img', 'https://x/y'));
});
