import type { ProcessingSpec } from '../pipeline/types.js';

export const ENGINE_BASE_URL = 'http://127.0.0.1:17891' as const;
export const ENGINE_HOST_PATTERN = 'http://127.0.0.1/*' as const;
export const ENGINE_PROTOCOL_VERSION = 1 as const;

export type EngineProfileState =
  | 'ready'
  | 'needs-download'
  | 'unavailable-hardware'
  | 'misconfigured-provider'
  | 'renderer-missing'
  | 'runtime-unavailable';

export type EnginePrivacyDescriptor = {
  imageLeavesDevice: boolean;
  ocrTextLeavesDevice: boolean | null;
  visualContextLeavesDevice: boolean;
};

export type EngineProfileDescriptor = {
  profileId: string;
  profileFingerprint: string;
  state: EngineProfileState;
  privacy: EnginePrivacyDescriptor;
  externalProviders: string[];
};

export type RemoteTransferConsentProof = {
  schemaVersion: 1;
  disclosureVersion: string;
  profileId: string;
  profileFingerprint: string;
  privacyDescriptor: EnginePrivacyDescriptor;
  externalProviderNames: string[];
  acceptedAt: number;
};

export type EngineCapabilities = {
  protocolVersion: 1;
  engineVersion: string;
  maxSourceBytes: number;
  maxResultBytes: number;
  supportedOutputKinds: string[];
  resultManifestSchemaVersions: number[];
  supportedSourceLanguages: string[];
  supportedTargetLanguages: string[];
  recommendedDefaults: Record<string, string>;
  hardware: { cpu: boolean; cuda: boolean; rocm: boolean; metal: boolean; vulkan: boolean };
  recommendedConcurrency: number;
  profiles: EngineProfileDescriptor[];
};

export type EngineJobState =
  | 'awaiting_source'
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'completed'
  | 'failed'
  | 'cancel_requested'
  | 'cancelled'
  | 'interrupted';

export type EngineResultDescriptor = {
  mime: 'image/webp' | 'image/png';
  bytes: number;
  sha256: string;
  width: number;
  height: number;
  manifestAvailable: boolean;
};

export type EngineCreateResponse = {
  engineTicket: string;
  state: EngineJobState;
  profileFingerprint: string;
  result?: EngineResultDescriptor;
};

export type EngineJobStatus = {
  state: Exclude<EngineJobState, 'completed'>;
  stage?: string;
  progress?: { completed: number; total: number };
  updatedAt: string;
  error?: { code?: string; message?: string; retryable?: boolean };
  result?: EngineResultDescriptor;
};

export type EngineConnectionSummary = {
  hostPermission: boolean;
  paired: boolean;
  reachable?: boolean;
  protocolVersion?: number;
  engineVersion?: string;
  profileId?: string;
  profileFingerprint?: string;
  profileState?: EngineProfileState;
  errorCode?: string;
};

export type EngineResultPayload = {
  blob: Blob;
  mimeType: 'image/webp' | 'image/png';
  byteLength: number;
  sha256: string;
  pixelWidth: number;
  pixelHeight: number;
  profileFingerprint: string;
  encoderSemantics: 'engine-exact-lossless-v1';
};

export type EngineCreateInput = {
  jobId: string;
  idempotencyKey: string;
  sourceSha256: string;
  sourceBytes: number;
  sourceMime: string;
  processingSpec: ProcessingSpec;
  expectedProfileFingerprint: string;
};

export type EngineModelInstallState = 'missing' | 'queued' | 'running' | 'ready' | 'succeeded' | 'failed' | 'cancelled';

export type EngineModelArtifact = {
  artifactId: string;
  revision: string;
  expectedFilename: string;
  bytes: number;
  sha256: string;
  licenseSpdx: string;
  redistribution: 'approved' | 'download-only';
  state: EngineModelInstallState;
  downloadedBytes: number;
  ticket?: string;
  error?: { code: string; message: string };
};

export type EngineModelCatalog = {
  schemaVersion: 1;
  catalogRevision: string;
  artifacts: EngineModelArtifact[];
};

export type EngineModelInstallStatus = {
  ticket?: string;
  artifactId: string;
  state: Exclude<EngineModelInstallState, 'missing'>;
  downloadedBytes: number;
  totalBytes: number;
  cancelRequested?: boolean;
  error?: { code: string; message: string };
};
