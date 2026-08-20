import { defineExtensionMessaging } from '@webext-core/messaging';
import type { StoredPageSession } from '../core/session-store.js';
import type { AcquisitionOutcome, AcquiredImage, PageSnapshot, RectSnapshot, ViewportSnapshot } from '../page/types.js';
import type { DeliverResultMessage, DeliveryAck, PageTranslateOutcome, PipelineStartResult } from '../pipeline/types.js';
import type { QueueSnapshot } from '../pipeline/coordinator.js';
import type { EngineCapabilities, EngineConnectionSummary, EngineModelCatalog, EngineModelInstallStatus } from '../engine/types.js';
import type { UiSettings } from '../ui/settings.js';
import type { TranslatePageResult, UiSnapshot } from '../ui/types.js';
import type { SafeDiagnostics } from '../ui/diagnostics.js';
import type { CacheGcReport, CacheStats } from '../cache/result-cache.js';
import type { PrivacyConsentState } from '../ui/privacy-consent.js';
import type { RemoteTransferConsentState } from '../ui/remote-transfer-consent.js';

export type SessionEnvelope = {
  sessionId: string;
  pageUrl: string;
  mainFrameOrigin: string;
};

export type PanelState = {
  session: StoredPageSession | null;
};

export interface ProtocolMap {
  'core:ping'(): { ok: true; now: number };
  'core:activate'(data: SessionEnvelope): PageSnapshot;
  'core:deactivate'(data: { sessionId: string }): void;
  'core:get-panel-state'(data: { tabId: number }): PanelState;

  'page:ready'(data: { sessionId: string; snapshot: PageSnapshot }): { accepted: boolean };
  'page:snapshot'(data: { sessionId: string; snapshot: PageSnapshot }): { accepted: boolean };
  'page:spa-navigation'(data: { sessionId: string; pageUrl: string }): SessionEnvelope | null;
  'page:acquire'(data: {
    sessionId: string;
    candidateId: string;
    allowScreenshot: boolean;
    previewOnPage: boolean;
  }): AcquisitionOutcome;
  'page:show-original'(data: { sessionId: string; candidateId: string }): { restored: boolean };
  'page:restore-all'(data: { sessionId: string }): void;
  'page:translate'(data: { sessionId: string; candidateId: string; allowScreenshot: boolean }): PageTranslateOutcome;
  'page:deliver-result'(data: DeliverResultMessage): DeliveryAck;
  'pipeline:intake'(data: { sessionId: string; candidateId: string; sourceRevision: number; acquired: AcquiredImage }): PipelineStartResult;

  'queue:translate'(data: {
    tabId: number;
    sessionId: string;
    candidateId: string;
    sourceRevision: number;
    allowScreenshot: boolean;
  }): PageTranslateOutcome;
  'queue:get-snapshot'(data: { tabId: number; sessionId: string }): QueueSnapshot | null;
  'queue:cancel'(data: { tabId: number; sessionId: string; jobId: string }): { cancelled: boolean };


  'ui:get-snapshot'(data: { tabId: number }): UiSnapshot;
  'ui:get-settings'(data: Record<string, never>): UiSettings;
  'ui:set-settings'(data: { settings: UiSettings }): UiSettings;
  'ui:get-privacy-consent'(data: Record<string, never>): PrivacyConsentState | null;
  'ui:accept-privacy-disclosure'(data: { tabId: number }): { accepted: true; activated: boolean };
  'ui:accept-remote-transfer-disclosure'(data: Record<string, never>): RemoteTransferConsentState;
  'ui:translate-page'(data: { tabId: number; sessionId: string; allowScreenshot: boolean }): TranslatePageResult;
  'ui:translate-candidate'(data: { tabId: number; sessionId: string; candidateId: string; sourceRevision: number; allowScreenshot: boolean }): PageTranslateOutcome;
  'ui:cancel-job'(data: { tabId: number; sessionId: string; jobId: string }): { cancelled: boolean };
  'ui:clear-cache'(data: Record<string, never>): CacheGcReport;
  'ui:get-cache-stats'(data: Record<string, never>): CacheStats;
  'ui:get-diagnostics'(data: { tabId: number }): SafeDiagnostics;
  'ui:get-capabilities'(data: Record<string, never>): EngineCapabilities | null;
  'ui:get-model-catalog'(data: Record<string, never>): EngineModelCatalog | null;
  'ui:install-model'(data: { artifactId: string }): EngineModelInstallStatus;
  'ui:get-model-install'(data: { ticket: string }): EngineModelInstallStatus;
  'ui:cancel-model-install'(data: { ticket: string }): EngineModelInstallStatus;

  'engine:get-state'(data: { probeAuthenticated: boolean }): EngineConnectionSummary;
  'engine:pair'(data: { token: string }): EngineConnectionSummary;
  'engine:disconnect'(data: Record<string, never>): { disconnected: true };

  'background:has-origin'(data: { sessionId: string; candidateId: string; origin: string }): { granted: boolean };
  'background:fetch-candidate'(data: {
    sessionId: string;
    candidateId: string;
    sourceUrl: string;
    forPresentation: boolean;
  }): AcquisitionOutcome;
  'background:capture-candidate'(data: {
    sessionId: string;
    candidateId: string;
    rect: RectSnapshot;
    viewport: ViewportSnapshot;
    forPresentation: boolean;
  }): AcquisitionOutcome;
}

export const { sendMessage, onMessage } = defineExtensionMessaging<ProtocolMap>();
