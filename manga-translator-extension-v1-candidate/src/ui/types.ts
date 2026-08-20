import type { StoredPageSession } from '../core/session-store.js';
import type { EngineCapabilities, EngineConnectionSummary } from '../engine/types.js';
import type { QueueSnapshot } from '../pipeline/coordinator.js';
import type { UiSettings } from './settings.js';

export type UiPageState = 'unsupported-tab' | 'inactive' | 'activating' | 'ready' | 'stale' | 'error';
export type UiEngineState = 'unknown' | 'permission-missing' | 'lna-required' | 'lna-denied' | 'offline' | 'pairing-required' | 'unauthorized' | 'connected';

export type UiErrorGroup = {
  code: string;
  count: number;
  scope: 'item' | 'session' | 'blocking';
};

export type UiSnapshot = {
  tabId: number;
  generatedAt: number;
  pageState: UiPageState;
  session: StoredPageSession | null;
  queue: QueueSnapshot | null;
  engine: EngineConnectionSummary;
  capabilities?: EngineCapabilities;
  settings: UiSettings;
  privacyConsentAccepted: boolean;
  remoteTransferConsentRequired: boolean;
  remoteTransferConsentAccepted: boolean;
  remoteTransferProviders: string[];
  errors: UiErrorGroup[];
};

export type TranslatePageResult = {
  queued: number;
  skippedFar: number;
  rejected: number;
  jobIds: string[];
};
