import { browser } from 'wxt/browser';
import { onMessage, sendMessage, type SessionEnvelope } from '../messaging/protocol.js';
import { PageSessionRuntime } from '../page/session.js';

const CONTROLLER_KEY = '__mtePhase3ContentController__';

type GlobalWithController = typeof globalThis & {
  [CONTROLLER_KEY]?: ContentController;
};

class ContentController {
  #runtime: PageSessionRuntime | null = null;
  #navigating = false;
  readonly #removeListeners: Array<() => void> = [];

  constructor() {
    this.#removeListeners.push(
      onMessage('core:activate', async ({ data }) => {
        if (this.#runtime?.envelope.sessionId === data.sessionId) return this.#runtime.snapshot();
        return await this.#activate(data);
      }),
      onMessage('core:deactivate', ({ data }) => {
        if (this.#runtime?.envelope.sessionId === data.sessionId) this.#disposeRuntime();
      }),
      onMessage('page:acquire', async ({ data }) => {
        if (!this.#runtime || this.#runtime.envelope.sessionId !== data.sessionId) {
          return {
            ok: false as const,
            failure: {
              reason: 'failed' as const,
              candidateId: data.candidateId,
              code: 'STALE_SESSION',
              message: 'Acquisition request belongs to a stale PageSession.'
            }
          };
        }
        return await this.#runtime.acquire(data.candidateId, {
          allowScreenshot: data.allowScreenshot,
          previewOnPage: data.previewOnPage
        });
      }),
      onMessage('page:show-original', ({ data }) => {
        if (!this.#runtime || this.#runtime.envelope.sessionId !== data.sessionId) return { restored: false };
        return { restored: this.#runtime.showOriginal(data.candidateId) };
      }),
      onMessage('page:restore-all', ({ data }) => {
        if (this.#runtime?.envelope.sessionId === data.sessionId) this.#runtime.restoreAll();
      }),
      onMessage('page:translate', async ({ data }) => {
        if (!this.#runtime || this.#runtime.envelope.sessionId !== data.sessionId) {
          return {
            ok: false as const,
            failure: {
              reason: 'failed' as const,
              candidateId: data.candidateId,
              code: 'STALE_SESSION',
              message: 'Translation request belongs to a stale PageSession.'
            }
          };
        }
        return await this.#runtime.translate(data.candidateId, data.allowScreenshot);
      }),
      onMessage('page:deliver-result', async ({ data, sender }) => {
        if (sender.id !== browser.runtime.id) {
          return { status: 'failed' as const, code: 'PRESENTATION_FAILED' as const, message: 'Rejected non-extension delivery sender.' };
        }
        if (!this.#runtime || this.#runtime.envelope.sessionId !== data.target.sessionId) {
          return { status: 'stale' as const, code: 'STALE_SESSION' as const };
        }
        return await this.#runtime.deliverResult(data);
      })
    );
  }

  async activate(envelope: SessionEnvelope): Promise<void> {
    await this.#activate(envelope);
  }

  dispose(): void {
    this.#disposeRuntime();
    for (const remove of this.#removeListeners.splice(0)) remove();
  }

  async #activate(envelope: SessionEnvelope) {
    this.#disposeRuntime();
    const runtime = new PageSessionRuntime(envelope, (pageUrl) => {
      void this.#handleSpaNavigation(pageUrl);
    });
    this.#runtime = runtime;
    const snapshot = runtime.start();
    await sendMessage('page:ready', { sessionId: envelope.sessionId, snapshot }).catch(() => ({ accepted: false }));
    return snapshot;
  }

  async #handleSpaNavigation(pageUrl: string): Promise<void> {
    const runtime = this.#runtime;
    if (!runtime || this.#navigating) return;
    this.#navigating = true;
    try {
      const next = await sendMessage('page:spa-navigation', {
        sessionId: runtime.envelope.sessionId,
        pageUrl
      });
      runtime.dispose();
      if (!next) {
        this.#runtime = null;
        return;
      }
      const replacement = new PageSessionRuntime(next, (url) => void this.#handleSpaNavigation(url));
      this.#runtime = replacement;
      const snapshot = replacement.start();
      await sendMessage('page:ready', { sessionId: next.sessionId, snapshot }).catch(() => ({ accepted: false }));
    } finally {
      this.#navigating = false;
    }
  }

  #disposeRuntime(): void {
    this.#runtime?.dispose();
    this.#runtime = null;
  }
}

export default defineContentScript({
  registration: 'runtime',
  world: 'ISOLATED',
  runAt: 'document_idle',
  main(ctx) {
    const global = globalThis as GlobalWithController;
    // WXT runtime injection is intentionally idempotent.
    global[CONTROLLER_KEY]?.dispose();
    const controller = new ContentController();
    global[CONTROLLER_KEY] = controller;
    ctx.onInvalidated(() => {
      controller.dispose();
      if (global[CONTROLLER_KEY] === controller) delete global[CONTROLLER_KEY];
    });
  }
});
