import { browser } from 'wxt/browser';
import type { UiSnapshot } from './types.js';

export type SafeDiagnostics = {
  extensionVersion: string;
  chromeVersion: string;
  platform: string;
  pageState: UiSnapshot['pageState'];
  grantedExternalOrigins: number;
  engine: { hostPermission: boolean; paired: boolean; reachable?: boolean; protocolVersion?: number; engineVersion?: string; profileId?: string; profileState?: string; errorCode?: string };
  queue: { active: number; recentFailed: number; cacheMiB: number; cacheEntries: number };
  errors: Array<{ code: string; count: number; scope: string }>;
};

export async function buildSafeDiagnostics(snapshot: UiSnapshot): Promise<SafeDiagnostics> {
  const permissions = await browser.permissions.getAll();
  const externalOrigins = (permissions.origins ?? []).filter((origin: string) => origin.startsWith('https://'));
  const failed = snapshot.queue?.recentTerminal.filter((item) => item.stage === 'failed').length ?? 0;
  const engine = snapshot.engine;
  return {
    extensionVersion: browser.runtime.getManifest().version,
    chromeVersion: chromeVersion(),
    platform: navigator.platform || 'unknown',
    pageState: snapshot.pageState,
    grantedExternalOrigins: externalOrigins.length,
    engine: {
      hostPermission: engine.hostPermission,
      paired: engine.paired,
      ...(engine.reachable !== undefined ? { reachable: engine.reachable } : {}),
      ...(engine.protocolVersion !== undefined ? { protocolVersion: engine.protocolVersion } : {}),
      ...(engine.engineVersion ? { engineVersion: engine.engineVersion } : {}),
      ...(engine.profileId ? { profileId: engine.profileId } : {}),
      ...(engine.profileState ? { profileState: engine.profileState } : {}),
      ...(engine.errorCode ? { errorCode: engine.errorCode } : {})
    },
    queue: {
      active: snapshot.queue?.active.length ?? 0,
      recentFailed: failed,
      cacheMiB: Math.round(((snapshot.queue?.cache.approxBytes ?? 0) / 1024 / 1024) * 10) / 10,
      cacheEntries: snapshot.queue?.cache.approxEntries ?? 0
    },
    errors: snapshot.errors.map(({ code, count, scope }) => ({ code, count, scope }))
  };
}

function chromeVersion(): string {
  const match = navigator.userAgent.match(/Chrome\/(\d+(?:\.\d+){0,3})/);
  return match?.[1] ?? 'unknown';
}
