import { browser } from 'wxt/browser';

export async function applyTrustedStoragePolicy(): Promise<void> {
  await browser.storage.local.setAccessLevel({ accessLevel: 'TRUSTED_CONTEXTS' });
  await browser.storage.session.setAccessLevel({ accessLevel: 'TRUSTED_CONTEXTS' });
  if (browser.storage.sync?.setAccessLevel) {
    await browser.storage.sync.setAccessLevel({ accessLevel: 'TRUSTED_CONTEXTS' });
  }
}
