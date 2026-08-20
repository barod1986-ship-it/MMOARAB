import { AppError } from '../core/errors.js';
import type { ProcessingSpec } from './types.js';
import { sha256Text } from './sha256.js';

export const DEFAULT_PROCESSING_SPEC: ProcessingSpec = Object.freeze({
  schemaVersion: 1,
  sourceLanguage: 'en',
  targetLanguage: 'ar',
  textRolePolicy: Object.freeze({
    translatableKinds: Object.freeze(['dialogue', 'narration'] as const),
    sfxAction: 'preserve-original',
    uncertainAction: 'preserve-original',
    revision: 'sfx-preserve-v1'
  }),
  output: Object.freeze({
    kind: 'translated-raster-image',
    preserveDimensions: true
  }),
  profileId: 'default-v1'
});

export function validateProcessingSpec(spec: ProcessingSpec): void {
  if (spec.schemaVersion !== 1) throw invalid('Unsupported ProcessingSpec schema version.');
  if (!languageToken(spec.sourceLanguage) || !languageToken(spec.targetLanguage)) throw invalid('Invalid language token.');
  if (spec.targetLanguage !== 'ar') throw invalid('V1 trusted product route requires Arabic target output.');
  if (spec.textRolePolicy.revision !== 'sfx-preserve-v1') throw invalid('Unsupported text-role policy revision.');
  if (spec.textRolePolicy.sfxAction !== 'preserve-original' || spec.textRolePolicy.uncertainAction !== 'preserve-original') {
    throw invalid('SFX and uncertain text must remain preserve-original in V1.');
  }
  if (
    spec.textRolePolicy.translatableKinds.length !== 2 ||
    spec.textRolePolicy.translatableKinds[0] !== 'dialogue' ||
    spec.textRolePolicy.translatableKinds[1] !== 'narration'
  ) {
    throw invalid('Only dialogue and narration are translatable under the frozen V1 contract.');
  }
  if (spec.output.kind !== 'translated-raster-image' || spec.output.preserveDimensions !== true) {
    throw invalid('V1 currently supports dimension-preserving translated raster output.');
  }
  if (!/^[a-z0-9][a-z0-9._-]{0,63}$/i.test(spec.profileId)) throw invalid('Invalid processing profile id.');
}

export function canonicalProcessingSpec(spec: ProcessingSpec): string {
  validateProcessingSpec(spec);
  // Explicit field order keeps the fingerprint independent from object insertion order.
  return JSON.stringify({
    schemaVersion: spec.schemaVersion,
    sourceLanguage: spec.sourceLanguage,
    targetLanguage: spec.targetLanguage,
    textRolePolicy: {
      translatableKinds: [...spec.textRolePolicy.translatableKinds],
      sfxAction: spec.textRolePolicy.sfxAction,
      uncertainAction: spec.textRolePolicy.uncertainAction,
      revision: spec.textRolePolicy.revision
    },
    output: {
      kind: spec.output.kind,
      preserveDimensions: spec.output.preserveDimensions
    },
    profileId: spec.profileId
  });
}

export async function processingSpecFingerprint(spec: ProcessingSpec): Promise<string> {
  return await sha256Text(canonicalProcessingSpec(spec));
}

export async function deriveWorkSignature(input: {
  sourceSha256: string;
  processingSpec: ProcessingSpec;
  engineProfileFingerprint: string;
}): Promise<string> {
  if (!/^[a-f0-9]{64}$/.test(input.sourceSha256)) throw invalid('Source SHA-256 must be lowercase hexadecimal.');
  if (!input.engineProfileFingerprint || input.engineProfileFingerprint.length > 512) throw invalid('Invalid engine profile fingerprint.');
  const canonical = canonicalProcessingSpec(input.processingSpec);
  // A versioned JSON tuple avoids ambiguous string concatenation while preserving the conceptual REV10 identity inputs.
  return await sha256Text(JSON.stringify(['mte-work-signature-v1', input.sourceSha256, canonical, input.engineProfileFingerprint]));
}

function languageToken(value: string): boolean {
  return value === 'auto' || /^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$/i.test(value);
}

function invalid(message: string): AppError {
  return new AppError('PROCESSING_SPEC_INVALID', message);
}
