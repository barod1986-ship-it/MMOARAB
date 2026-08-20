import { expect, it } from 'vitest';
import { evaluateRemotePolicy, exactOriginPattern } from '../../src/page/acquisition/remote-policy.js';

it('main-frame origin is allowed under activeTab authority', () => {
  expect(
    evaluateRemotePolicy({
      candidateUrl: 'http://reader.example/ch/p1.png',
      knownCandidateUrl: 'http://reader.example/ch/p1.png',
      sessionMainOrigin: 'http://reader.example',
      exactOriginGranted: false
    })
  ).toEqual({ allowed: true, authority: 'active-tab-main-origin', requestOrigin: 'http://reader.example' });
});

it('external https requires exact optional permission', () => {
  expect(
    evaluateRemotePolicy({
      candidateUrl: 'https://cdn.example/p1.webp',
      knownCandidateUrl: 'https://cdn.example/p1.webp',
      sessionMainOrigin: 'https://reader.example',
      exactOriginGranted: false
    })
  ).toEqual({ allowed: false, reason: 'permission-needed', origin: 'https://cdn.example' });
});

it('external http is rejected instead of asking for a broad permission', () => {
  expect(
    evaluateRemotePolicy({
      candidateUrl: 'http://cdn.example/p1.webp',
      knownCandidateUrl: 'http://cdn.example/p1.webp',
      sessionMainOrigin: 'https://reader.example',
      exactOriginGranted: true
    })
  ).toEqual({ allowed: false, reason: 'invalid-url' });
});

it('candidate URL must exactly match the session record', () => {
  expect(
    evaluateRemotePolicy({
      candidateUrl: 'https://cdn.example/p2.webp',
      knownCandidateUrl: 'https://cdn.example/p1.webp',
      sessionMainOrigin: 'https://reader.example',
      exactOriginGranted: true
    })
  ).toEqual({ allowed: false, reason: 'candidate-mismatch' });
});

it('redirect to another origin requires a separate exact-origin grant', () => {
  expect(
    evaluateRemotePolicy({
      candidateUrl: 'https://cdn.example/p1.webp',
      knownCandidateUrl: 'https://cdn.example/p1.webp',
      sessionMainOrigin: 'https://reader.example',
      exactOriginGranted: true,
      finalResponseUrl: 'https://other.example/p1.webp',
      finalOriginGranted: false
    })
  ).toEqual({ allowed: false, reason: 'permission-needed', origin: 'https://other.example' });
});

it('redirect can be consumed only after the final HTTPS origin is separately granted', () => {
  expect(
    evaluateRemotePolicy({
      candidateUrl: 'https://cdn.example/p1.webp',
      knownCandidateUrl: 'https://cdn.example/p1.webp',
      sessionMainOrigin: 'https://reader.example',
      exactOriginGranted: true,
      finalResponseUrl: 'https://other.example/p1.webp',
      finalOriginGranted: true
    })
  ).toEqual({ allowed: true, authority: 'optional-exact-origin', requestOrigin: 'https://other.example' });
});

it('exact pattern only accepts https origins', () => {
  expect(exactOriginPattern('https://cdn.example')).toBe('https://cdn.example/*');
  expect(exactOriginPattern('http://cdn.example')).toBeNull();
});
