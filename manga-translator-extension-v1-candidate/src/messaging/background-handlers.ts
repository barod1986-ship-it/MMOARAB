import { browser } from 'wxt/browser';
import { onMessage } from './protocol.js';
import { SessionStore, type StoredPageSession } from '../core/session-store.js';
import type { PipelineCoordinator } from '../pipeline/coordinator.js';
import type { LocalProcessingGateway } from '../engine/local-processing-gateway.js';
import { UiSettingsStore, cachePolicyFromSettings, processingSpecFromSettings } from '../ui/settings.js';
import { buildUiSnapshot } from '../ui/snapshot.js';
import { buildSafeDiagnostics } from '../ui/diagnostics.js';
import { CachePolicyStore } from '../cache/cache-policy.js';
import { ResultCache } from '../cache/result-cache.js';
import type { ActivationCoordinator } from '../core/activation.js';
import { PrivacyConsentStore } from '../ui/privacy-consent.js';
import { RemoteTransferConsentStore, requiresRemoteTransferConsent } from '../ui/remote-transfer-consent.js';
import {
  AcquisitionHandoffStore,
  captureKnownCandidate,
  containsExactOrigin,
  fetchKnownCandidate
} from '../core/background-acquisition.js';

export function registerBackgroundHandlers(options: {
  sessions: SessionStore;
  acquisitions: AcquisitionHandoffStore;
  pipeline: PipelineCoordinator;
  engine: LocalProcessingGateway;
  activation: ActivationCoordinator;
  privacyConsent?: PrivacyConsentStore;
  remoteTransferConsent?: RemoteTransferConsentStore;
  uiSettings?: UiSettingsStore;
}): Array<() => void> {
  const { sessions, acquisitions, pipeline, engine, activation } = options;
  const privacyConsent = options.privacyConsent ?? new PrivacyConsentStore();
  const remoteTransferConsent = options.remoteTransferConsent ?? new RemoteTransferConsentStore();
  const uiSettings = options.uiSettings ?? new UiSettingsStore();
  const cachePolicies = new CachePolicyStore();
  const resultCache = new ResultCache(cachePolicies);
  return [
    onMessage('core:ping', () => ({ ok: true as const, now: Date.now() })),

    onMessage('core:get-panel-state', async (message) => {
      if (!panelStateSenderAllowed(message.sender, message.data.tabId)) return { session: null };
      return { session: await sessions.get(message.data.tabId) };
    }),

    onMessage('page:ready', async (message) => {
      if (!await privacyConsent.isAccepted()) return { accepted: false };
      const session = await sessions.get(message.sender.tab?.id ?? -1);
      if (!validContentSender(session, message.sender, message.data.sessionId, false)) return { accepted: false };
      const updated = await sessions.updateSnapshot(
        session.tabId,
        message.data.sessionId,
        message.data.snapshot,
        message.sender.documentId
      );
      return { accepted: Boolean(updated) };
    }),

    onMessage('page:snapshot', async (message) => {
      if (!await privacyConsent.isAccepted()) return { accepted: false };
      const session = await sessions.get(message.sender.tab?.id ?? -1);
      if (!validContentSender(session, message.sender, message.data.sessionId, true)) return { accepted: false };
      const updated = await sessions.updateSnapshot(
        session.tabId,
        message.data.sessionId,
        message.data.snapshot,
        message.sender.documentId
      );
      return { accepted: Boolean(updated) };
    }),

    onMessage('page:spa-navigation', async (message) => {
      if (!await privacyConsent.isAccepted()) return null;
      const session = await sessions.get(message.sender.tab?.id ?? -1);
      if (!validContentSender(session, message.sender, message.data.sessionId, true)) return null;
      let nextUrl: URL;
      try {
        nextUrl = new URL(message.data.pageUrl);
      } catch {
        return null;
      }
      if (nextUrl.origin !== session.mainFrameOrigin) return null;
      const next = await sessions.rotateForSpa(session.tabId, nextUrl.href, message.sender.documentId);
      if (!next) return null;
      return { sessionId: next.sessionId, pageUrl: next.pageUrl, mainFrameOrigin: next.mainFrameOrigin };
    }),

    onMessage('pipeline:intake', async (message) => {
      if (!await privacyConsent.isAccepted()) return { jobId: '', stage: 'failed' as const, applied: false, stale: true, errorCode: 'PRIVACY_CONSENT_REQUIRED' };
      const session = await sessions.get(message.sender.tab?.id ?? -1);
      if (!validContentSender(session, message.sender, message.data.sessionId, true)) {
        return {
          jobId: '',
          stage: 'failed' as const,
          applied: false,
          stale: true,
          errorCode: 'STALE_SESSION'
        };
      }
      return await pipeline.start({
        session,
        candidateId: message.data.candidateId,
        sourceRevision: message.data.sourceRevision,
        acquired: message.data.acquired
      });
    }),

    onMessage('queue:translate', async (message) => {
      if (!await privacyConsent.isAccepted()) return staleFailure(message.data.candidateId, 'PRIVACY_CONSENT_REQUIRED');
      const session = await sessions.get(message.data.tabId);
      if (!queueCommandSenderAllowed(session, message.sender, message.data.tabId, message.data.sessionId)) {
        return staleFailure(message.data.candidateId);
      }
      const candidate = session.candidates[message.data.candidateId];
      if (!candidate || candidate.sourceRevision !== message.data.sourceRevision) {
        return {
          ok: false as const,
          failure: {
            reason: 'failed' as const,
            candidateId: message.data.candidateId,
            code: 'STALE_TARGET',
            message: 'Candidate source changed before queue admission.'
          }
        };
      }
      return await pipeline.requestTranslation({
        session,
        candidateId: message.data.candidateId,
        sourceRevision: message.data.sourceRevision,
        allowScreenshot: message.data.allowScreenshot
      });
    }),

    onMessage('queue:get-snapshot', async (message) => {
      const session = await sessions.get(message.data.tabId);
      if (!queueCommandSenderAllowed(session, message.sender, message.data.tabId, message.data.sessionId)) return null;
      return await pipeline.snapshot(session.sessionId);
    }),

    onMessage('queue:cancel', async (message) => {
      const session = await sessions.get(message.data.tabId);
      if (!queueCommandSenderAllowed(session, message.sender, message.data.tabId, message.data.sessionId)) return { cancelled: false };
      await pipeline.cancelJob(message.data.jobId, 'explicit-user');
      return { cancelled: true };
    }),

    onMessage('ui:get-snapshot', async (message) => {
      requireTrustedUiSender(message.sender);
      return await buildUiSnapshot({ tabId: message.data.tabId, sessions, pipeline, engine, settings: uiSettings, privacyConsent, remoteTransferConsent });
    }),

    onMessage('ui:get-settings', async (message) => {
      requireTrustedUiSender(message.sender);
      return await uiSettings.get();
    }),

    onMessage('ui:set-settings', async (message) => {
      requireTrustedUiSender(message.sender);
      await uiSettings.set(message.data.settings);
      await cachePolicies.set(cachePolicyFromSettings(message.data.settings));
      return await uiSettings.get();
    }),

    onMessage('ui:get-privacy-consent', async (message) => {
      requireTrustedUiSender(message.sender);
      return await privacyConsent.get();
    }),

    onMessage('ui:accept-privacy-disclosure', async (message) => {
      requireTrustedUiSender(message.sender);
      // Consent is product-level and remains valid even if the Side Panel is opened
      // while Chrome is showing an unsupported internal page. Page activation is a
      // separate step and only occurs for an explicit HTTP(S) tab.
      await privacyConsent.accept();
      const tab = await browser.tabs.get(message.data.tabId);
      if (tab.id === undefined || typeof tab.url !== 'string' || !/^https?:/i.test(tab.url)) {
        return { accepted: true as const, activated: false };
      }
      await activation.activateFromUi(tab);
      return { accepted: true as const, activated: true };
    }),

    onMessage('ui:accept-remote-transfer-disclosure', async (message) => {
      requireTrustedUiSender(message.sender);
      if (!await privacyConsent.isAccepted()) throw new Error('Local processing disclosure must be accepted first.');
      const settings = await uiSettings.get();
      const capabilities = await engine.getCapabilities({ force: true });
      const profile = capabilities.profiles.find((candidate) => candidate.profileId === settings.profileId);
      if (!profile || profile.state !== 'ready') throw new Error('Selected production profile is not ready for consent.');
      if (!requiresRemoteTransferConsent(profile)) throw new Error('Selected profile does not transfer user data externally.');
      return await remoteTransferConsent.accept(profile);
    }),

    onMessage('ui:translate-page', async (message) => {
      if (!await privacyConsent.isAccepted()) return { queued: 0, skippedFar: 0, rejected: 1, jobIds: [] };
      const session = await sessions.get(message.data.tabId);
      if (!uiCommandSenderAllowed(session, message.sender, message.data.tabId, message.data.sessionId)) {
        return { queued: 0, skippedFar: 0, rejected: 1, jobIds: [] };
      }
      const settings = await uiSettings.get();
      return await pipeline.enqueuePageTranslations({
        session,
        processingSpec: processingSpecFromSettings(settings),
        allowScreenshot: message.data.allowScreenshot
      });
    }),

    onMessage('ui:translate-candidate', async (message) => {
      if (!await privacyConsent.isAccepted()) return staleFailure(message.data.candidateId, 'PRIVACY_CONSENT_REQUIRED');
      const session = await sessions.get(message.data.tabId);
      if (!uiCommandSenderAllowed(session, message.sender, message.data.tabId, message.data.sessionId)) return staleFailure(message.data.candidateId);
      const settings = await uiSettings.get();
      return await pipeline.requestTranslation({
        session,
        candidateId: message.data.candidateId,
        sourceRevision: message.data.sourceRevision,
        allowScreenshot: message.data.allowScreenshot,
        processingSpec: processingSpecFromSettings(settings)
      });
    }),

    onMessage('ui:cancel-job', async (message) => {
      const session = await sessions.get(message.data.tabId);
      if (!uiCommandSenderAllowed(session, message.sender, message.data.tabId, message.data.sessionId)) return { cancelled: false };
      await pipeline.cancelJob(message.data.jobId, 'explicit-user');
      return { cancelled: true };
    }),

    onMessage('ui:clear-cache', async (message) => {
      requireTrustedUiSender(message.sender);
      return await resultCache.clear();
    }),

    onMessage('ui:get-cache-stats', async (message) => {
      requireTrustedUiSender(message.sender);
      return await resultCache.getStats();
    }),

    onMessage('ui:get-diagnostics', async (message) => {
      requireTrustedUiSender(message.sender);
      const snapshot = await buildUiSnapshot({ tabId: message.data.tabId, sessions, pipeline, engine, settings: uiSettings, privacyConsent, remoteTransferConsent });
      return await buildSafeDiagnostics(snapshot);
    }),

    onMessage('ui:get-capabilities', async (message) => {
      requireTrustedUiSender(message.sender);
      return await engine.getCapabilities().catch(() => null);
    }),

    onMessage('ui:get-model-catalog', async (message) => {
      requireTrustedUiSender(message.sender);
      return await engine.getModelCatalog().catch(() => null);
    }),

    onMessage('ui:install-model', async (message) => {
      requireTrustedUiSender(message.sender);
      return await engine.installModel(message.data.artifactId);
    }),

    onMessage('ui:get-model-install', async (message) => {
      requireTrustedUiSender(message.sender);
      return await engine.getModelInstall(message.data.ticket);
    }),

    onMessage('ui:cancel-model-install', async (message) => {
      requireTrustedUiSender(message.sender);
      return await engine.cancelModelInstall(message.data.ticket);
    }),

    onMessage('engine:get-state', async (message) => {
      requireTrustedUiSender(message.sender);
      return await engine.getConnectionSummary({ probeAuthenticated: message.data.probeAuthenticated });
    }),

    onMessage('engine:pair', async (message) => {
      requireTrustedUiSender(message.sender);
      return await engine.pair(message.data.token);
    }),

    onMessage('engine:disconnect', async (message) => {
      requireTrustedUiSender(message.sender);
      await engine.disconnect();
      return { disconnected: true as const };
    }),

    onMessage('background:has-origin', async (message) => {
      if (!await privacyConsent.isAccepted()) return { granted: false };
      const session = await sessions.get(message.sender.tab?.id ?? -1);
      if (!validContentSender(session, message.sender, message.data.sessionId, true)) return { granted: false };
      const known = session.candidates[message.data.candidateId];
      if (!known?.sourceUrl) return { granted: false };
      try {
        if (new URL(known.sourceUrl).origin !== message.data.origin) return { granted: false };
      } catch {
        return { granted: false };
      }
      return { granted: await containsExactOrigin(message.data.origin) };
    }),

    onMessage('background:fetch-candidate', async (message) => {
      if (!await privacyConsent.isAccepted()) return staleFailure(message.data.candidateId, 'PRIVACY_CONSENT_REQUIRED');
      const session = await sessions.get(message.sender.tab?.id ?? -1);
      if (!validContentSender(session, message.sender, message.data.sessionId, true)) {
        return staleFailure(message.data.candidateId);
      }
      return await fetchKnownCandidate({
        session,
        candidateId: message.data.candidateId,
        sourceUrl: message.data.sourceUrl,
        forPresentation: message.data.forPresentation,
        acquisitionStore: acquisitions,
        sessionStillActive: async () => (await sessions.get(session.tabId))?.sessionId === session.sessionId
      });
    }),

    onMessage('background:capture-candidate', async (message) => {
      if (!await privacyConsent.isAccepted()) return staleFailure(message.data.candidateId, 'PRIVACY_CONSENT_REQUIRED');
      const session = await sessions.get(message.sender.tab?.id ?? -1);
      if (!validContentSender(session, message.sender, message.data.sessionId, true)) {
        return staleFailure(message.data.candidateId);
      }
      return await captureKnownCandidate({
        session,
        candidateId: message.data.candidateId,
        rect: message.data.rect,
        viewport: message.data.viewport,
        forPresentation: message.data.forPresentation,
        acquisitionStore: acquisitions,
        sessionStillActive: async () => (await sessions.get(session.tabId))?.sessionId === session.sessionId
      });
    })
  ];
}

type MessageSenderLike = {
  id?: string;
  tab?: { id?: number };
  frameId?: number;
  documentId?: string;
  url?: string;
};

function validContentSender(
  session: StoredPageSession | null,
  sender: MessageSenderLike,
  sessionId: string,
  requireDocumentMatch: boolean
): session is StoredPageSession {
  if (!session) return false;
  if (sender.id !== browser.runtime.id) return false;
  if (sender.tab?.id !== session.tabId) return false;
  if ((sender.frameId ?? 0) !== 0) return false;
  if (session.sessionId !== sessionId) return false;
  if (requireDocumentMatch && session.documentId !== undefined && sender.documentId !== session.documentId) return false;
  return true;
}


function queueCommandSenderAllowed(
  session: StoredPageSession | null,
  sender: MessageSenderLike,
  requestedTabId: number,
  sessionId: string
): session is StoredPageSession {
  if (!session || session.tabId !== requestedTabId || session.sessionId !== sessionId) return false;
  if (sender.id !== browser.runtime.id) return false;
  if (sender.tab?.id !== undefined) {
    return validContentSender(session, sender, sessionId, true);
  }
  return sender.url?.startsWith(browser.runtime.getURL('/')) ?? false;
}

function uiCommandSenderAllowed(
  session: StoredPageSession | null,
  sender: MessageSenderLike,
  requestedTabId: number,
  sessionId: string
): session is StoredPageSession {
  return Boolean(session && session.tabId === requestedTabId && session.sessionId === sessionId && trustedExtensionPageSender(sender));
}

function requireTrustedUiSender(sender: MessageSenderLike): void {
  if (!trustedExtensionPageSender(sender)) throw new Error('Unauthorized extension UI sender.');
}

function panelStateSenderAllowed(sender: MessageSenderLike, requestedTabId: number): boolean {
  if (sender.id !== browser.runtime.id) return false;
  if (sender.tab?.id !== undefined) return sender.tab.id === requestedTabId;
  return sender.url?.startsWith(browser.runtime.getURL('/')) ?? false;
}

function staleFailure(candidateId: string, code = 'STALE_SESSION') {
  return {
    ok: false as const,
    failure: {
      reason: 'failed' as const,
      candidateId,
      code,
      message: code === 'PRIVACY_CONSENT_REQUIRED'
        ? 'Current privacy disclosure must be accepted before page data is processed.'
        : 'Message sender does not match the active PageSession/document.'
    }
  };
}

function trustedExtensionPageSender(sender: MessageSenderLike): boolean {
  if (sender.id !== browser.runtime.id || sender.tab?.id !== undefined) return false;
  return sender.url?.startsWith(browser.runtime.getURL('/')) ?? false;
}
