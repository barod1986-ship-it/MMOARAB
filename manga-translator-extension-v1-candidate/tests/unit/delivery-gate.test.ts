import { describe, expect, it } from 'vitest';
import { isTargetFresh } from '../../src/pipeline/delivery-gate.js';
import type { StoredPageSession } from '../../src/core/session-store.js';
import type { PageTargetRef } from '../../src/pipeline/types.js';

const target: PageTargetRef = {
  sessionId: 'session_1',
  tabId: 7,
  documentId: 'doc_1',
  candidateId: 'candidate_1',
  sourceRevision: 3
};

function session(overrides: Partial<StoredPageSession> = {}): StoredPageSession {
  return {
    sessionId: 'session_1',
    tabId: 7,
    windowId: 1,
    pageUrl: 'https://reader.example/chapter/1',
    mainFrameOrigin: 'https://reader.example',
    startedAt: 1,
    mode: 'generic',
    status: 'active',
    documentId: 'doc_1',
    candidates: {
      candidate_1: {
        candidateId: 'candidate_1',
        sourceKey: 'source-key',
        sourceRevision: 3,
        kind: 'img'
      }
    },
    ...overrides
  };
}

describe('Phase 2 delivery freshness gate', () => {
  it('accepts only the exact active session/document/candidate revision', () => {
    expect(isTargetFresh(session(), target)).toBe(true);
  });

  it('rejects a recycled candidate whose source revision changed', () => {
    const changed = session();
    changed.candidates.candidate_1!.sourceRevision = 4;
    expect(isTargetFresh(changed, target)).toBe(false);
  });

  it('rejects navigation/document replacement and inactive sessions', () => {
    expect(isTargetFresh(session({ documentId: 'doc_2' }), target)).toBe(false);
    expect(isTargetFresh(session({ status: 'inactive' }), target)).toBe(false);
  });
});
