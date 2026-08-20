import { browser } from 'wxt/browser';
import en from './locales/en.json';
import ar from './locales/ar.json';
import type { UiLocalePreference } from './settings.js';

type Catalog = Record<string, string>;
const CATALOGS: Record<'en' | 'ar', Catalog> = { en, ar };

export type MessageKey = keyof typeof en;

export function effectiveLocale(preference: UiLocalePreference): 'en' | 'ar' {
  if (preference === 'en' || preference === 'ar') return preference;
  const ui = browser.i18n.getUILanguage().toLowerCase();
  return ui.startsWith('ar') ? 'ar' : 'en';
}

export function createTranslator(preference: UiLocalePreference): (key: MessageKey, substitutions?: string | string[]) => string {
  const locale = effectiveLocale(preference);
  return (key, substitutions) => {
    if (preference === 'system') {
      const chromeMessage = browser.i18n.getMessage(key, substitutions);
      if (chromeMessage) return chromeMessage;
    }
    let value = CATALOGS[locale][key] ?? CATALOGS.en[key] ?? String(key);
    const values = typeof substitutions === 'string' ? [substitutions] : substitutions ?? [];
    values.forEach((part, index) => { value = value.replaceAll(`$${index + 1}`, part); });
    return value;
  };
}

export function applyDocumentLocale(preference: UiLocalePreference): void {
  const locale = effectiveLocale(preference);
  document.documentElement.lang = locale;
  document.documentElement.dir = locale === 'ar' ? 'rtl' : 'ltr';
}
