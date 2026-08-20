import type { AcquiredImage, AcquisitionFailure, AcquisitionMethod } from '../page/types.js';

export type PageTargetRef = {
  sessionId: string;
  tabId: number;
  documentId: string;
  candidateId: string;
  sourceRevision: number;
};

export type BinaryPurpose = 'source' | 'result';
export type BinaryOwnerType = 'job' | 'work' | 'cache';
export type BinaryLeaseRole = 'source' | 'result' | 'delivery' | 'cache';

export type BinaryRef = {
  binaryId: string;
  store: 'indexeddb-transient';
  byteLength: number;
  mimeType: string;
  createdAt: number;
  sha256?: string;
};

export type BinaryOwnerRef = {
  ownerType: BinaryOwnerType;
  ownerId: string;
  role: BinaryLeaseRole;
};

export type ProcessingSpec = {
  schemaVersion: 1;
  sourceLanguage: string | 'auto';
  targetLanguage: string;
  textRolePolicy: {
    translatableKinds: readonly ['dialogue', 'narration'];
    sfxAction: 'preserve-original';
    uncertainAction: 'preserve-original';
    revision: 'sfx-preserve-v1';
  };
  output: {
    kind: 'translated-raster-image';
    preserveDimensions: true;
  };
  profileId: string;
};

export type PriorityBand = 'P0' | 'P1' | 'P2' | 'P3' | 'P4' | 'P5' | 'P6';
export type CandidateVisibility = 'visible' | 'near' | 'far';

export type SchedulingHint = {
  priorityBand: PriorityBand;
  visibility: CandidateVisibility;
  readingOrder: number;
  explicit: boolean;
  estimatedSourceBytes?: number;
  acquisitionMethod?: AcquisitionMethod;
};

export type CancellationKind = 'explicit-user' | 'navigation-stale' | 'session-close';

export type PipelineStage =
  | 'waiting-admission'
  | 'acquiring'
  | 'staging-source'
  | 'hashing'
  | 'waiting-work'
  | 'joined-work'
  | 'delivering'
  | 'ready-result'
  | 'applied'
  | 'failed'
  | 'cancelled'
  | 'stale';

export type WorkStage =
  | 'queued'
  | 'submitting'
  | 'processing'
  | 'fetching-result'
  | 'validating-result'
  | 'ready'
  | 'failed'
  | 'cancelling'
  | 'cancelled';

export type RasterMetadata = {
  pixelWidth: number;
  pixelHeight: number;
  capture?: AcquiredImage['capture'];
};

export type JobRecord = {
  jobId: string;
  runtimeSessionId: string;
  target: PageTargetRef;
  processingSpec: ProcessingSpec;
  processingSpecFingerprint?: string;
  engineProfileFingerprint: string;
  source?: BinaryRef;
  sourceSha256?: string;
  sourceRaster?: RasterMetadata;
  result?: BinaryRef;
  resultRaster?: RasterMetadata;
  resultEncoderSemantics?: 'engine-exact-lossless-v1';
  workId?: string;
  signature?: string;
  cacheKey?: string;
  cacheHit?: boolean;
  allowScreenshot: boolean;
  schedulingHint: SchedulingHint;
  stage: PipelineStage;
  attempt: number;
  notBefore?: number;
  lastErrorCode?: string;
  cancelRequested: boolean;
  cancellationKind?: CancellationKind;
  staleForDelivery: boolean;
  createdAt: number;
  updatedAt: number;
  terminalAt?: number;
};

export type WorkRecord = {
  workId: string;
  runtimeSessionId: string;
  jobSignature: string;
  sourceBinaryId: string;
  sourceSha256: string;
  sourceRaster: RasterMetadata;
  processingSpecFingerprint: string;
  processingSpec?: ProcessingSpec;
  engineProfileFingerprint: string;
  stage: WorkStage;
  engineTicket?: string;
  engineStage?: string;
  engineProgress?: { completed: number; total: number };
  resultBinaryId?: string;
  resultRaster?: RasterMetadata;
  resultEncoderSemantics?: 'engine-exact-lossless-v1';
  suppressCachePromotion: boolean;
  attempt: number;
  notBefore?: number;
  lastErrorCode?: string;
  createdAt: number;
  updatedAt: number;
};

export type PageTranslateOutcome =
  | { ok: true; result: PipelineStartResult }
  | { ok: false; failure: AcquisitionFailure };

export type PipelineStartResult = {
  jobId: string;
  stage: PipelineStage;
  signature?: string;
  workId?: string;
  cacheHit?: boolean;
  applied: boolean;
  stale: boolean;
  errorCode?: string;
};

export type DeliveryAck =
  | { status: 'applied' }
  | { status: 'stored' }
  | { status: 'stale'; code: 'STALE_SESSION' | 'STALE_TARGET' }
  | { status: 'failed'; code: 'PRESENTATION_FAILED'; message: string };

export type DeliverResultMessage = {
  target: PageTargetRef;
  presentation: {
    autoShow: boolean;
    showCompactControls: boolean;
    locale: 'en' | 'ar';
  };
  result: {
    mimeType: 'image/webp' | 'image/png';
    byteLength: number;
    pixelWidth: number;
    pixelHeight: number;
    blob: Blob;
    capture?: AcquiredImage['capture'];
  };
};
