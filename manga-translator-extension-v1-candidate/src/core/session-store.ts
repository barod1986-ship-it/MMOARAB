import { browser } from 'wxt/browser';
import { newSessionId } from '../shared/ids.js';
import type { KnownCandidateRecord, PageSession, PageSnapshot } from '../page/types.js';

const STORAGE_KEY = 'phase1.activeSessions';

export type StoredPageSession = PageSession & {
  status: 'activating' | 'active' | 'inactive' | 'error';
  candidates: Record<string, KnownCandidateRecord>;
  lastSnapshot?: PageSnapshot;
  lastError?: string;
};

type SessionMap = Record<string, StoredPageSession>;

export class SessionStore {
  #writeTail: Promise<void> = Promise.resolve();

  async create(tabId: number, windowId: number, pageUrl: string): Promise<StoredPageSession> {
    const url = new URL(pageUrl);
    const session: StoredPageSession = {
      sessionId: newSessionId(),
      tabId,
      windowId,
      pageUrl: url.href,
      mainFrameOrigin: url.origin,
      startedAt: Date.now(),
      mode: 'generic',
      status: 'activating',
      candidates: {}
    };

    await this.#mutate((all) => {
      all[String(tabId)] = session;
    });
    return session;
  }

  async rotateForSpa(tabId: number, pageUrl: string, documentId?: string): Promise<StoredPageSession | null> {
    const nextUrl = new URL(pageUrl);
    let result: StoredPageSession | null = null;

    await this.#mutate((all) => {
      const old = all[String(tabId)];
      if (!old || nextUrl.origin !== old.mainFrameOrigin) return;

      result = {
        sessionId: newSessionId(),
        tabId: old.tabId,
        windowId: old.windowId,
        pageUrl: nextUrl.href,
        mainFrameOrigin: old.mainFrameOrigin,
        startedAt: Date.now(),
        mode: old.mode,
        status: 'active',
        candidates: {},
        ...(documentId ? { documentId } : {})
      };
      all[String(tabId)] = result;
    });

    return result;
  }

  async get(tabId: number): Promise<StoredPageSession | null> {
    await this.#writeTail;
    const all = await this.#readAll();
    return all[String(tabId)] ?? null;
  }

  async set(session: StoredPageSession): Promise<void> {
    await this.#mutate((all) => {
      all[String(session.tabId)] = session;
    });
  }

  async updateSnapshot(
    tabId: number,
    sessionId: string,
    snapshot: PageSnapshot,
    documentId?: string
  ): Promise<StoredPageSession | null> {
    let result: StoredPageSession | null = null;

    await this.#mutate((all) => {
      const session = all[String(tabId)];
      if (!session || session.sessionId !== sessionId) return;

      // A delayed observer flush must never overwrite a newer snapshot for the same session.
      if (session.lastSnapshot && session.lastSnapshot.updatedAt > snapshot.updatedAt) {
        result = session;
        return;
      }

      session.status = 'active';
      session.pageUrl = snapshot.pageUrl;
      session.lastSnapshot = snapshot;
      session.candidates = Object.fromEntries(
        snapshot.candidates.map((candidate) => [
          candidate.candidateId,
          {
            candidateId: candidate.candidateId,
            kind: candidate.kind,
            sourceKey: candidate.sourceKey,
            sourceRevision: candidate.sourceRevision,
            ...(candidate.sourceUrl ? { sourceUrl: candidate.sourceUrl } : {}),
            ...(candidate.sourceOrigin ? { sourceOrigin: candidate.sourceOrigin } : {}),
            ...(candidate.naturalWidth !== undefined ? { naturalWidth: candidate.naturalWidth } : {}),
            ...(candidate.naturalHeight !== undefined ? { naturalHeight: candidate.naturalHeight } : {}),
            ...(candidate.visibility ? { visibility: candidate.visibility } : {}),
            ...(candidate.orderHint !== undefined ? { orderHint: candidate.orderHint } : {}),
            ...(candidate.estimatedSourceBytes !== undefined ? { estimatedSourceBytes: candidate.estimatedSourceBytes } : {}),
            state: candidate.state
          }
        ])
      );
      if (documentId) session.documentId = documentId;
      result = session;
    });

    return result;
  }

  async markError(tabId: number, message: string): Promise<void> {
    await this.#mutate((all) => {
      const session = all[String(tabId)];
      if (!session) return;
      session.status = 'error';
      session.lastError = message;
    });
  }

  async remove(tabId: number): Promise<void> {
    await this.#mutate((all) => {
      delete all[String(tabId)];
    });
  }

  async list(): Promise<StoredPageSession[]> {
    await this.#writeTail;
    return Object.values(await this.#readAll());
  }

  async #readAll(): Promise<SessionMap> {
    const result = await browser.storage.session.get(STORAGE_KEY);
    const value = result[STORAGE_KEY];
    if (!isSessionMap(value)) return {};

    const sessions: SessionMap = {};
    for (const [tabId, session] of Object.entries(value)) {
      if (isStoredPageSession(session)) sessions[tabId] = session;
    }
    return sessions;
  }

  async #writeAll(value: SessionMap): Promise<void> {
    await browser.storage.session.set({ [STORAGE_KEY]: value });
  }

  async #mutate(mutator: (all: SessionMap) => void): Promise<void> {
    const operation = this.#writeTail.then(async () => {
      const all = await this.#readAll();
      mutator(all);
      await this.#writeAll(all);
    });

    // Keep the queue usable even if a storage operation fails; the current caller still receives the failure.
    this.#writeTail = operation.catch(() => undefined);
    await operation;
  }
}

function isSessionMap(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isStoredPageSession(value: unknown): value is StoredPageSession {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const session = value as Partial<StoredPageSession>;
  return (
    typeof session.sessionId === 'string' &&
    typeof session.tabId === 'number' &&
    Number.isInteger(session.tabId) &&
    typeof session.windowId === 'number' &&
    Number.isInteger(session.windowId) &&
    typeof session.pageUrl === 'string' &&
    typeof session.mainFrameOrigin === 'string' &&
    typeof session.startedAt === 'number' &&
    (session.mode === 'generic' || session.mode === 'adapter') &&
    (session.status === 'activating' || session.status === 'active' || session.status === 'inactive' || session.status === 'error') &&
    typeof session.candidates === 'object' &&
    session.candidates !== null &&
    !Array.isArray(session.candidates)
  );
}
