import type { SessionStore } from '../core/session-store.js';
import type { LocalProcessingGateway } from '../engine/local-processing-gateway.js';
import type { PipelineCoordinator } from '../pipeline/coordinator.js';
import type { UiSettingsStore } from './settings.js';
import type { PrivacyConsentStore } from './privacy-consent.js';
import { requiresRemoteTransferConsent, type RemoteTransferConsentStore } from './remote-transfer-consent.js';
import type { UiErrorGroup, UiPageState, UiSnapshot } from './types.js';

export async function buildUiSnapshot(input: {
  tabId: number;
  sessions: SessionStore;
  pipeline: PipelineCoordinator;
  engine: LocalProcessingGateway;
  settings: UiSettingsStore;
  privacyConsent: PrivacyConsentStore;
  remoteTransferConsent: RemoteTransferConsentStore;
}): Promise<UiSnapshot> {
  const [session, settings, privacyConsentAccepted, engine] = await Promise.all([
    input.sessions.get(input.tabId),
    input.settings.get(),
    input.privacyConsent.isAccepted(),
    input.engine.getConnectionSummary({ probeAuthenticated: true }).catch(() => ({ hostPermission: false, paired: false, reachable: false, errorCode: 'ENGINE_REQUEST_FAILED' }))
  ]);
  const queue = session ? await input.pipeline.snapshot(session.sessionId) : null;
  let capabilities;
  if (engine.hostPermission && engine.paired && engine.reachable) {
    capabilities = await input.engine.getCapabilities().catch(() => undefined);
  }
  const selectedProfile = capabilities?.profiles.find((profile) => profile.profileId === settings.profileId);
  const remoteTransferConsentRequired = selectedProfile ? requiresRemoteTransferConsent(selectedProfile) : false;
  const remoteTransferConsentAccepted = selectedProfile
    ? await input.remoteTransferConsent.isAcceptedForProfile(selectedProfile).catch(() => false)
    : false;
  const effectiveEngine = selectedProfile ? {
    ...engine,
    profileId: selectedProfile.profileId,
    profileFingerprint: selectedProfile.profileFingerprint,
    profileState: selectedProfile.state
  } : engine;
  const currentPageState = pageState(session);
  return {
    tabId: input.tabId,
    generatedAt: Date.now(),
    pageState: currentPageState,
    session,
    queue,
    engine: effectiveEngine,
    ...(capabilities ? { capabilities } : {}),
    settings,
    privacyConsentAccepted,
    remoteTransferConsentRequired,
    remoteTransferConsentAccepted,
    remoteTransferProviders: selectedProfile ? [...selectedProfile.externalProviders] : [],
    errors: groupErrors(
      queue?.recentTerminal.map((item) => item.errorCode).filter((code): code is string => Boolean(code)) ?? [],
      effectiveEngine,
      Boolean(capabilities && !selectedProfile),
      currentPageState
    )
  };
}

function pageState(session: Awaited<ReturnType<SessionStore['get']>>): UiPageState {
  if (!session) return 'inactive';
  if (session.status === 'activating') return 'activating';
  if (session.status === 'active') return session.documentId ? 'ready' : 'activating';
  if (session.status === 'error') return 'error';
  return 'inactive';
}

function groupErrors(codes: string[], engine: UiSnapshot['engine'], selectedProfileMissing: boolean, pageState: UiPageState): UiErrorGroup[] {
  const all = [...codes];
  if (pageState !== 'ready') return groupCodes(all);
  if (!engine.hostPermission) all.unshift('ENGINE_HOST_PERMISSION_MISSING');
  else if (!engine.paired) all.unshift('ENGINE_PAIRING_REQUIRED');
  else if (engine.reachable === false) all.unshift(engine.errorCode ?? 'ENGINE_OFFLINE');
  else if (selectedProfileMissing) all.unshift('ENGINE_PROFILE_NOT_FOUND');
  else if (engine.profileState && engine.profileState !== 'ready') all.unshift('ENGINE_PROFILE_NOT_READY');
  return groupCodes(all);
}

function groupCodes(codes: string[]): UiErrorGroup[] {
  const map = new Map<string, number>();
  for (const code of codes) map.set(code, (map.get(code) ?? 0) + 1);
  return [...map.entries()].map(([code, count]) => ({ code, count, scope: scopeFor(code) }));
}

function scopeFor(code: string): UiErrorGroup['scope'] {
  const blocking = new Set([
    'ENGINE_HOST_PERMISSION_MISSING', 'ENGINE_OFFLINE', 'ENGINE_PAIRING_REQUIRED', 'ENGINE_UNAUTHORIZED',
    'ENGINE_PROTOCOL_UNSUPPORTED', 'ENGINE_CAPABILITY_MISSING', 'ENGINE_PROFILE_NOT_FOUND',
    'ENGINE_PROFILE_NOT_READY', 'ENGINE_PROFILE_CHANGED', 'ENGINE_REQUEST_FAILED', 'PROCESSING_SPEC_INVALID'
  ]);
  if (blocking.has(code)) return 'blocking';
  if (code === 'STALE_SESSION' || code === 'STALE_DOCUMENT' || code === 'BINARY_STORE_FAILED') return 'session';
  return 'item';
}
