import { browser } from 'wxt/browser';
import { CACHE_TTL_MS } from '../shared/constants.js';
import type { ProcessingSpec } from '../pipeline/types.js';
import type { CachePolicy } from '../cache/cache-policy.js';

const STORAGE_KEY = 'phase6.uiSettings';

export type UiLocalePreference = 'system' | 'en' | 'ar';
export type UiTheme = 'system' | 'light' | 'dark';

export type UiSettings = {
  schemaVersion: 1;
  uiLocale: UiLocalePreference;
  sourceLanguage: string | 'auto';
  targetLanguage: 'ar';
  profileId: string;
  theme: UiTheme;
  showCompactControls: boolean;
  autoShowTranslatedResult: boolean;
  cacheEnabled: boolean;
  cacheMaxMiB: 128 | 256 | 512;
};

export const DEFAULT_UI_SETTINGS: UiSettings = Object.freeze({
  schemaVersion: 1,
  uiLocale: 'system',
  sourceLanguage: 'en',
  targetLanguage: 'ar',
  profileId: 'default-v1',
  theme: 'system',
  showCompactControls: true,
  autoShowTranslatedResult: true,
  cacheEnabled: true,
  cacheMaxMiB: 256
});

export class UiSettingsStore {
  async get(): Promise<UiSettings> {
    const raw = (await browser.storage.local.get(STORAGE_KEY))[STORAGE_KEY];
    return isUiSettings(raw) ? structuredClone(raw) : structuredClone(DEFAULT_UI_SETTINGS);
  }

  async set(next: UiSettings): Promise<void> {
    if (!isUiSettings(next)) throw new Error('Invalid UI settings.');
    await browser.storage.local.set({ [STORAGE_KEY]: structuredClone(next) });
  }
}

export function processingSpecFromSettings(settings: UiSettings): ProcessingSpec {
  return {
    schemaVersion: 1,
    sourceLanguage: settings.sourceLanguage,
    targetLanguage: settings.targetLanguage,
    textRolePolicy: {
      translatableKinds: ['dialogue', 'narration'],
      sfxAction: 'preserve-original',
      uncertainAction: 'preserve-original',
      revision: 'sfx-preserve-v1'
    },
    output: { kind: 'translated-raster-image', preserveDimensions: true },
    profileId: settings.profileId
  };
}

export function cachePolicyFromSettings(settings: UiSettings): CachePolicy {
  return {
    enabled: settings.cacheEnabled,
    maxBytes: settings.cacheMaxMiB * 1024 * 1024,
    ttlMs: CACHE_TTL_MS,
    lowWaterRatio: 0.8
  };
}

function isUiSettings(value: unknown): value is UiSettings {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const v = value as Partial<UiSettings>;
  return v.schemaVersion === 1 &&
    (v.uiLocale === 'system' || v.uiLocale === 'en' || v.uiLocale === 'ar') &&
    (v.sourceLanguage === 'auto' || (typeof v.sourceLanguage === 'string' && /^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$/i.test(v.sourceLanguage))) &&
    v.targetLanguage === 'ar' &&
    typeof v.profileId === 'string' && /^[a-z0-9][a-z0-9._-]{0,63}$/i.test(v.profileId) &&
    (v.theme === 'system' || v.theme === 'light' || v.theme === 'dark') &&
    typeof v.showCompactControls === 'boolean' &&
    typeof v.autoShowTranslatedResult === 'boolean' &&
    typeof v.cacheEnabled === 'boolean' &&
    (v.cacheMaxMiB === 128 || v.cacheMaxMiB === 256 || v.cacheMaxMiB === 512);
}
