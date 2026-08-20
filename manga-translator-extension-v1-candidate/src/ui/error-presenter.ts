export type ErrorPresentation = {
  titleKey: string;
  bodyKey: string;
  action: 'recheck-engine' | 'open-engine-setup' | 'retry' | 'grant-permission' | 'none';
  severity: 'item' | 'session' | 'blocking';
};

const MAP: Record<string, ErrorPresentation> = {
  ENGINE_HOST_PERMISSION_MISSING: { titleKey: 'errorEnginePermissionTitle', bodyKey: 'errorEnginePermissionBody', action: 'open-engine-setup', severity: 'blocking' },
  ENGINE_OFFLINE: { titleKey: 'errorEngineOfflineTitle', bodyKey: 'errorEngineOfflineBody', action: 'recheck-engine', severity: 'blocking' },
  ENGINE_PAIRING_REQUIRED: { titleKey: 'errorPairingTitle', bodyKey: 'errorPairingBody', action: 'open-engine-setup', severity: 'blocking' },
  ENGINE_UNAUTHORIZED: { titleKey: 'errorPairingTitle', bodyKey: 'errorPairingBody', action: 'open-engine-setup', severity: 'blocking' },
  ENGINE_PROFILE_NOT_READY: { titleKey: 'errorProfileTitle', bodyKey: 'errorProfileBody', action: 'open-engine-setup', severity: 'blocking' },
  ENGINE_PROFILE_NOT_FOUND: { titleKey: 'errorProfileTitle', bodyKey: 'errorProfileBody', action: 'open-engine-setup', severity: 'blocking' },
  ENGINE_PROFILE_CHANGED: { titleKey: 'errorProfileTitle', bodyKey: 'errorProfileBody', action: 'recheck-engine', severity: 'blocking' },
  ENGINE_PROTOCOL_UNSUPPORTED: { titleKey: 'errorInternalTitle', bodyKey: 'errorInternalBody', action: 'open-engine-setup', severity: 'blocking' },
  ENGINE_CAPABILITY_MISSING: { titleKey: 'errorProfileTitle', bodyKey: 'errorProfileBody', action: 'open-engine-setup', severity: 'blocking' },
  ENGINE_REQUEST_FAILED: { titleKey: 'errorEngineOfflineTitle', bodyKey: 'errorEngineOfflineBody', action: 'recheck-engine', severity: 'blocking' },
  PERMISSION_NEEDED: { titleKey: 'errorImagePermissionTitle', bodyKey: 'errorImagePermissionBody', action: 'grant-permission', severity: 'item' },
  CAPTURE_AWAITING_FOCUS: { titleKey: 'errorCaptureVisibleTitle', bodyKey: 'errorCaptureVisibleBody', action: 'retry', severity: 'item' },
  UNSUPPORTED_SOURCE_MIME: { titleKey: 'errorUnsupportedImageTitle', bodyKey: 'errorUnsupportedImageBody', action: 'none', severity: 'item' },
  STALE_TARGET: { titleKey: 'errorStaleTitle', bodyKey: 'errorStaleBody', action: 'none', severity: 'item' },
  STALE_SESSION: { titleKey: 'errorStaleTitle', bodyKey: 'errorStaleBody', action: 'none', severity: 'session' },
  INTERNAL: { titleKey: 'errorInternalTitle', bodyKey: 'errorInternalBody', action: 'none', severity: 'session' }
};

export function presentationForError(code: string): ErrorPresentation {
  return MAP[code] ?? { titleKey: 'errorGenericTitle', bodyKey: 'errorGenericBody', action: 'retry', severity: 'item' };
}
