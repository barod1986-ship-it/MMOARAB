import { describe, expect, it } from 'vitest';
import {
  DEFAULT_PROCESSING_SPEC,
  canonicalProcessingSpec,
  deriveWorkSignature,
  processingSpecFingerprint
} from '../../src/pipeline/processing-spec.js';

const SHA256_HEX = /^[a-f0-9]{64}$/;

describe('Phase 2 pipeline identity', () => {
  it('canonicalizes the frozen en→ar / SFX-preserve contract deterministically', () => {
    const first = canonicalProcessingSpec(structuredClone(DEFAULT_PROCESSING_SPEC));
    const reordered = {
      profileId: 'default-v1',
      output: { preserveDimensions: true as const, kind: 'translated-raster-image' as const },
      textRolePolicy: {
        revision: 'sfx-preserve-v1' as const,
        uncertainAction: 'preserve-original' as const,
        sfxAction: 'preserve-original' as const,
        translatableKinds: ['dialogue', 'narration'] as const
      },
      targetLanguage: 'ar',
      sourceLanguage: 'en',
      schemaVersion: 1 as const
    };
    expect(canonicalProcessingSpec(reordered)).toBe(first);
  });

  it('changes WorkSignature when source/spec/profile identity changes', async () => {
    const sourceA = 'a'.repeat(64);
    const sourceB = 'b'.repeat(64);
    const one = await deriveWorkSignature({ sourceSha256: sourceA, processingSpec: DEFAULT_PROCESSING_SPEC, engineProfileFingerprint: 'mock-raster-png-v1' });
    const same = await deriveWorkSignature({ sourceSha256: sourceA, processingSpec: structuredClone(DEFAULT_PROCESSING_SPEC), engineProfileFingerprint: 'mock-raster-png-v1' });
    const otherSource = await deriveWorkSignature({ sourceSha256: sourceB, processingSpec: DEFAULT_PROCESSING_SPEC, engineProfileFingerprint: 'mock-raster-png-v1' });
    const otherProfile = await deriveWorkSignature({ sourceSha256: sourceA, processingSpec: DEFAULT_PROCESSING_SPEC, engineProfileFingerprint: 'mock-raster-png-v2' });
    expect(one).toBe(same);
    expect(one).not.toBe(otherSource);
    expect(one).not.toBe(otherProfile);
    expect(SHA256_HEX.test(one)).toBe(true);
  });

  it('fingerprints ProcessingSpec separately for future cache identity', async () => {
    expect(SHA256_HEX.test(await processingSpecFingerprint(DEFAULT_PROCESSING_SPEC))).toBe(true);
  });
});
