import { browser } from 'wxt/browser';
import type { EnginePrivacyDescriptor, EngineProfileDescriptor } from '../engine/types.js';

export const REMOTE_TRANSFER_DISCLOSURE_VERSION = '2026-08-19.remote-transfer.v1';
const STORAGE_KEY = 'phase9.remoteTransferConsent';

export type RemoteTransferConsentState = {
  schemaVersion: 1;
  disclosureVersion: string;
  profileId: string;
  profileFingerprint: string;
  privacyDescriptor: EnginePrivacyDescriptor;
  externalProviderNames: string[];
  acceptedAt: number;
};

export function requiresRemoteTransferConsent(profile: EngineProfileDescriptor): boolean {
  return profile.privacy.imageLeavesDevice || profile.privacy.ocrTextLeavesDevice === true || profile.privacy.visualContextLeavesDevice;
}

export function remoteTransferConsentMatches(state: RemoteTransferConsentState, profile: EngineProfileDescriptor): boolean {
  if (state.disclosureVersion !== REMOTE_TRANSFER_DISCLOSURE_VERSION) return false;
  if (state.profileId !== profile.profileId || state.profileFingerprint !== profile.profileFingerprint) return false;
  if (!samePrivacy(state.privacyDescriptor, profile.privacy)) return false;
  if (!sameStrings(state.externalProviderNames, profile.externalProviders)) return false;
  return requiresRemoteTransferConsent(profile) && profile.externalProviders.length > 0;
}

export class RemoteTransferConsentStore {
  async get(profile: EngineProfileDescriptor): Promise<RemoteTransferConsentState | null> {
    const raw = (await browser.storage.local.get(STORAGE_KEY))[STORAGE_KEY];
    if (!isRemoteTransferConsentState(raw) || !remoteTransferConsentMatches(raw, profile)) return null;
    return structuredClone(raw);
  }

  async isAcceptedForProfile(profile: EngineProfileDescriptor): Promise<boolean> {
    if (!requiresRemoteTransferConsent(profile)) return profile.privacy.ocrTextLeavesDevice !== null;
    return Boolean(await this.get(profile));
  }

  async accept(profile: EngineProfileDescriptor): Promise<RemoteTransferConsentState> {
    if (!requiresRemoteTransferConsent(profile)) throw new Error('Selected profile does not require remote-transfer consent.');
    if (profile.privacy.ocrTextLeavesDevice === null || profile.externalProviders.length === 0) {
      throw new Error('Selected profile does not provide a complete remote-transfer disclosure.');
    }
    const state: RemoteTransferConsentState = {
      schemaVersion: 1,
      disclosureVersion: REMOTE_TRANSFER_DISCLOSURE_VERSION,
      profileId: profile.profileId,
      profileFingerprint: profile.profileFingerprint,
      privacyDescriptor: structuredClone(profile.privacy),
      externalProviderNames: [...profile.externalProviders],
      acceptedAt: Date.now()
    };
    await browser.storage.local.set({ [STORAGE_KEY]: state });
    return structuredClone(state);
  }

  async clear(): Promise<void> {
    await browser.storage.local.remove(STORAGE_KEY);
  }
}

function isRemoteTransferConsentState(value: unknown): value is RemoteTransferConsentState {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const state = value as Partial<RemoteTransferConsentState>;
  return state.schemaVersion === 1 &&
    typeof state.disclosureVersion === 'string' &&
    typeof state.profileId === 'string' && state.profileId.length > 0 &&
    typeof state.profileFingerprint === 'string' && /^sha256:[a-f0-9]{64}$/.test(state.profileFingerprint) &&
    isPrivacyDescriptor(state.privacyDescriptor) &&
    Array.isArray(state.externalProviderNames) && state.externalProviderNames.length > 0 &&
    state.externalProviderNames.every((name) => typeof name === 'string' && name.trim().length > 0) &&
    new Set(state.externalProviderNames).size === state.externalProviderNames.length &&
    typeof state.acceptedAt === 'number' && Number.isFinite(state.acceptedAt) && state.acceptedAt > 0;
}

function isPrivacyDescriptor(value: unknown): value is EnginePrivacyDescriptor {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const privacy = value as Partial<EnginePrivacyDescriptor>;
  return typeof privacy.imageLeavesDevice === 'boolean' &&
    (typeof privacy.ocrTextLeavesDevice === 'boolean' || privacy.ocrTextLeavesDevice === null) &&
    typeof privacy.visualContextLeavesDevice === 'boolean';
}

function samePrivacy(a: EnginePrivacyDescriptor, b: EnginePrivacyDescriptor): boolean {
  return a.imageLeavesDevice === b.imageLeavesDevice &&
    a.ocrTextLeavesDevice === b.ocrTextLeavesDevice &&
    a.visualContextLeavesDevice === b.visualContextLeavesDevice;
}

function sameStrings(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((value, index) => value === b[index]);
}
