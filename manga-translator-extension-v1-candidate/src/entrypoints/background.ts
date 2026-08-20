import { browser } from 'wxt/browser';
import { ActivationCoordinator } from '../core/activation.js';
import { AcquisitionHandoffStore } from '../core/background-acquisition.js';
import { applyTrustedStoragePolicy } from '../core/lifecycle.js';
import { SessionStore } from '../core/session-store.js';
import { registerBackgroundHandlers } from '../messaging/background-handlers.js';
import { RuntimeSessionStore } from '../state/runtime-session.js';
import { BinaryStore } from '../binary/binary-store.js';
import { JobStore } from '../pipeline/job-store.js';
import { LocalProcessingGateway } from '../engine/local-processing-gateway.js';
import { PipelineCoordinator } from '../pipeline/coordinator.js';
import { QUEUE_WAKE_ALARM } from '../shared/constants.js';
import { UiSettingsStore } from '../ui/settings.js';
import { PrivacyConsentStore } from '../ui/privacy-consent.js';
import { RemoteTransferConsentStore } from '../ui/remote-transfer-consent.js';
import { sendMessage } from '../messaging/protocol.js';

export default defineBackground(() => {
  const sessions = new SessionStore();
  const runtimeSessions = new RuntimeSessionStore();
  const acquisitions = new AcquisitionHandoffStore();
  const binaries = new BinaryStore();
  const jobs = new JobStore();
  const remoteTransferConsent = new RemoteTransferConsentStore();
  const gateway = new LocalProcessingGateway(undefined, remoteTransferConsent);
  const uiSettings = new UiSettingsStore();
  const privacyConsent = new PrivacyConsentStore();
  const pipeline = new PipelineCoordinator({ sessions, runtimeSessions, jobs, binaries, acquisitions, gateway, uiSettings });
  const activation = new ActivationCoordinator(sessions);
  registerBackgroundHandlers({ sessions, acquisitions, pipeline, engine: gateway, activation, privacyConsent, remoteTransferConsent, uiSettings });

  void applyTrustedStoragePolicy().catch((error) => console.error('[mte] storage policy failed', error));

  const deactivateSessionsUntilCurrentConsent = async (): Promise<void> => {
    // Work admitted under an older disclosure version must not resume under a new
    // disclosure until the user has re-consented and explicitly requests it again.
    for (const job of await jobs.listNonTerminal()) {
      await pipeline.cancelJob(job.jobId, 'explicit-user').catch(() => undefined);
    }
    for (const session of await sessions.list()) {
      await sendMessage('core:deactivate', { sessionId: session.sessionId }, { tabId: session.tabId, frameId: 0 }).catch(() => undefined);
      await sessions.remove(session.tabId);
    }
  };

  const reconcileIfConsented = async (): Promise<void> => {
    if (!await privacyConsent.isAccepted()) {
      await deactivateSessionsUntilCurrentConsent();
      return;
    }
    await pipeline.reconcile();
  };

  // defineBackground runs whenever MV3 starts a fresh worker instance. A disclosure-version
  // change invalidates old consent, so stale sessions are explicitly deactivated before any
  // pipeline reconciliation is allowed to resume.
  void reconcileIfConsented().catch((error) => console.error('[mte] consent/reconciliation failed', error));

  browser.runtime.onStartup.addListener(() => {
    void reconcileIfConsented().catch((error) => console.error('[mte] startup consent/reconciliation failed', error));
  });

  browser.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name !== QUEUE_WAKE_ALARM) return;
    void (async () => {
      if (!await privacyConsent.isAccepted()) return;
      await pipeline.pump('alarm');
    })().catch((error) => console.error('[mte] queue alarm pump failed', error));
  });

  browser.action.onClicked.addListener((tab) => {
    if (tab.id === undefined) return;
    // Always open the disclosure/control surface synchronously inside the user gesture.
    const panelOpen = browser.sidePanel.open({ tabId: tab.id });
    void (async () => {
      await panelOpen.catch(() => undefined);
      if (!await privacyConsent.isAccepted()) return;
      await activation.activateFromUi(tab);
    })().catch(async (error) => {
      console.error('[mte] activation failed', error);
      if (tab.id !== undefined) await sessions.markError(tab.id, error instanceof Error ? error.message : 'Activation failed');
    });
  });

  browser.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.status !== 'complete') return;
    void (async () => {
      if (!await privacyConsent.isAccepted()) return;
      await activation.reinjectAfterNavigation(tabId, tab.url);
    })().catch((error) => {
      console.warn('[mte] reinjection skipped', error);
    });
  });

  browser.tabs.onRemoved.addListener((tabId) => {
    void sessions.remove(tabId);
  });
});
