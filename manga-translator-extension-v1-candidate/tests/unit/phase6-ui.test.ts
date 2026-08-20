import { describe, expect, it } from 'vitest';
import { cachePolicyFromSettings, DEFAULT_UI_SETTINGS, processingSpecFromSettings } from '../../src/ui/settings.js';
import { presentationForError } from '../../src/ui/error-presenter.js';

describe('Phase 6 trusted UI contracts', () => {
  it('builds ProcessingSpec from settings without exposing an SFX translation option', () => {
    const spec = processingSpecFromSettings({ ...DEFAULT_UI_SETTINGS, sourceLanguage: 'ja', profileId: 'fixture-v1' });
    expect(spec.sourceLanguage).toBe('ja');
    expect(spec.targetLanguage).toBe('ar');
    expect(spec.profileId).toBe('fixture-v1');
    expect(spec.textRolePolicy.sfxAction).toBe('preserve-original');
    expect(spec.textRolePolicy.uncertainAction).toBe('preserve-original');
    expect(spec.textRolePolicy.translatableKinds).toEqual(['dialogue', 'narration']);
  });

  it('maps the only supported cache sizes to byte budgets', () => {
    expect(cachePolicyFromSettings({ ...DEFAULT_UI_SETTINGS, cacheMaxMiB: 128 }).maxBytes).toBe(128 * 1024 * 1024);
    expect(cachePolicyFromSettings({ ...DEFAULT_UI_SETTINGS, cacheMaxMiB: 512 }).maxBytes).toBe(512 * 1024 * 1024);
  });

  it('keeps connection/profile blockers actionable and item failures non-blocking', () => {
    expect(presentationForError('ENGINE_PROFILE_NOT_FOUND').severity).toBe('blocking');
    expect(presentationForError('ENGINE_REQUEST_FAILED').action).toBe('recheck-engine');
    expect(presentationForError('UNSUPPORTED_SOURCE_MIME').severity).toBe('item');
  });
});
