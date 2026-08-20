import { browser } from 'wxt/browser';

export const PRIVACY_DISCLOSURE_VERSION = '2026-08-19.v1';
const STORAGE_KEY = 'phase8.privacyConsent';

export type PrivacyConsentState = {
  schemaVersion: 1;
  disclosureVersion: string;
  acceptedAt: number;
};

export class PrivacyConsentStore {
  async get(): Promise<PrivacyConsentState | null> {
    const raw = (await browser.storage.local.get(STORAGE_KEY))[STORAGE_KEY];
    if (!isPrivacyConsentState(raw)) return null;
    if (raw.disclosureVersion !== PRIVACY_DISCLOSURE_VERSION) return null;
    return structuredClone(raw);
  }

  async isAccepted(): Promise<boolean> {
    return Boolean(await this.get());
  }

  async accept(): Promise<PrivacyConsentState> {
    const state: PrivacyConsentState = {
      schemaVersion: 1,
      disclosureVersion: PRIVACY_DISCLOSURE_VERSION,
      acceptedAt: Date.now()
    };
    await browser.storage.local.set({ [STORAGE_KEY]: state });
    return structuredClone(state);
  }
}

function isPrivacyConsentState(value: unknown): value is PrivacyConsentState {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const state = value as Partial<PrivacyConsentState>;
  return state.schemaVersion === 1 &&
    typeof state.disclosureVersion === 'string' &&
    typeof state.acceptedAt === 'number' && Number.isFinite(state.acceptedAt) && state.acceptedAt > 0;
}
