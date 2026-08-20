export type CandidateKind = 'img' | 'canvas' | 'viewport-region';
export type CandidateVisibility = 'visible' | 'near' | 'far';

export type CandidateState =
  | 'detected'
  | 'waiting-load'
  | 'ready'
  | 'permission-needed'
  | 'acquired'
  | 'translated'
  | 'stale';

export type RectSnapshot = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type ViewportSnapshot = {
  width: number;
  height: number;
  visualOffsetLeft: number;
  visualOffsetTop: number;
};

export type PageSession = {
  sessionId: string;
  tabId: number;
  windowId: number;
  documentId?: string;
  pageUrl: string;
  mainFrameOrigin: string;
  startedAt: number;
  mode: 'generic' | 'adapter';
};

export type PageImageCandidate = {
  candidateId: string;
  kind: CandidateKind;
  sourceUrl?: string;
  sourceOrigin?: string;
  sourceKey: string;
  sourceRevision: number;
  rect: RectSnapshot;
  naturalWidth?: number;
  naturalHeight?: number;
  groupId?: string;
  orderHint?: number;
  confidence: number;
  adapterId?: string;
  state: CandidateState;
  nearViewport?: boolean;
  visibility?: CandidateVisibility;
  estimatedSourceBytes?: number;
};

export type CandidateSummary = Omit<PageImageCandidate, 'rect'> & {
  rect: RectSnapshot;
};

export type PageSnapshot = {
  sessionId: string;
  pageUrl: string;
  candidates: CandidateSummary[];
  updatedAt: number;
};

export type AcquisitionMethod =
  | 'dom-fetch'
  | 'canvas-snapshot'
  | 'extension-fetch'
  | 'viewport-capture';

export type AcquisitionAuthority =
  | 'page-origin'
  | 'active-tab-main-origin'
  | 'optional-exact-origin'
  | 'visual-capture';

export type AcquiredImage = {
  candidateId: string;
  method: AcquisitionMethod;
  blob?: Blob;
  acquisitionId?: string;
  mimeType: string;
  pixelWidth?: number;
  pixelHeight?: number;
  sourceUrl?: string;
  authority?: AcquisitionAuthority;
  capture?: {
    mode: 'full-image' | 'viewport-segment';
    rect?: RectSnapshot;
  };
};

export type AcquisitionFailure =
  | { reason: 'permission-needed'; origin: string; candidateId: string }
  | { reason: 'unsupported'; candidateId: string }
  | { reason: 'capture-required'; candidateId: string }
  | { reason: 'failed'; candidateId: string; code: string; message: string };

export type AcquisitionOutcome =
  | { ok: true; image: AcquiredImage }
  | { ok: false; failure: AcquisitionFailure };

export type KnownCandidateRecord = {
  candidateId: string;
  kind: CandidateKind;
  sourceKey: string;
  sourceRevision: number;
  sourceUrl?: string;
  sourceOrigin?: string;
  naturalWidth?: number;
  naturalHeight?: number;
  visibility?: CandidateVisibility;
  orderHint?: number;
  estimatedSourceBytes?: number;
  state?: CandidateState;
};
