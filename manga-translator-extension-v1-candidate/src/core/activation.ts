import { browser } from 'wxt/browser';
import { sendMessage, type SessionEnvelope } from '../messaging/protocol.js';
import { AppError } from './errors.js';
import { SessionStore, type StoredPageSession } from './session-store.js';

export class ActivationCoordinator {
  readonly #sessions: SessionStore;

  constructor(sessions: SessionStore) {
    this.#sessions = sessions;
  }

  async activateFromAction(tab: { id?: number; windowId?: number; url?: string }, panelOpen: Promise<void>): Promise<void> {
    // sidePanel.open() was invoked synchronously by the action listener; awaiting it here is safe.
    await panelOpen.catch(() => undefined);
    const tabId = tab.id;
    if (tabId === undefined) throw new AppError('INVALID_TAB', 'Action did not provide a tab id.');
    const fullTab = tab.url && tab.windowId !== undefined ? tab : await browser.tabs.get(tabId);
    const pageUrl = validatePageUrl(fullTab.url);
    const windowId = fullTab.windowId;
    const session = await this.#sessions.create(tabId, windowId, pageUrl);
    await this.#injectAndStart(session);
  }

  async activateFromUi(tab: { id?: number; windowId?: number; url?: string }): Promise<void> {
    const tabId = tab.id;
    if (tabId === undefined) throw new AppError('INVALID_TAB', 'UI activation did not provide a tab id.');
    const fullTab = tab.url && tab.windowId !== undefined ? tab : await browser.tabs.get(tabId);
    const pageUrl = validatePageUrl(fullTab.url);
    const session = await this.#sessions.create(tabId, fullTab.windowId, pageUrl);
    await this.#injectAndStart(session);
  }

  async reinjectAfterNavigation(tabId: number, tabUrl?: string): Promise<void> {
    const existing = await this.#sessions.get(tabId);
    if (!existing) return;
    const fullTab = tabUrl ? { id: tabId, windowId: existing.windowId, url: tabUrl } : await browser.tabs.get(tabId);
    let url: URL;
    try {
      url = new URL(validatePageUrl(fullTab.url));
    } catch {
      await this.#sessions.remove(tabId);
      return;
    }
    if (url.origin !== existing.mainFrameOrigin) {
      await this.#sessions.remove(tabId);
      return;
    }

    const next = await this.#sessions.create(tabId, existing.windowId, url.href);
    try {
      await this.#injectAndStart(next);
    } catch {
      // Same-origin activeTab normally survives navigation. If it does not, the user must reactivate explicitly.
      await this.#sessions.remove(tabId);
    }
  }

  async #injectAndStart(session: StoredPageSession): Promise<void> {
    await browser.scripting.executeScript({
      target: { tabId: session.tabId, frameIds: [0] },
      files: ['content-scripts/manga.js']
    });
    const envelope: SessionEnvelope = {
      sessionId: session.sessionId,
      pageUrl: session.pageUrl,
      mainFrameOrigin: session.mainFrameOrigin
    };
    const snapshot = await sendMessage('core:activate', envelope, { tabId: session.tabId, frameId: 0 });
    await this.#sessions.updateSnapshot(session.tabId, session.sessionId, snapshot);
  }
}

function validatePageUrl(raw: string | undefined): string {
  if (!raw) throw new AppError('UNSUPPORTED_PAGE', 'The current tab does not expose a page URL.');
  const url = new URL(raw);
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new AppError('UNSUPPORTED_PAGE', `Unsupported page scheme: ${url.protocol}`);
  }
  return url.href;
}
