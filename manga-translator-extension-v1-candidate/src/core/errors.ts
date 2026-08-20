export const ERROR_CODES = [
  'INVALID_TAB',
  'UNSUPPORTED_PAGE',
  'NO_ACTIVE_SESSION',
  'STALE_SESSION',
  'STALE_DOCUMENT',
  'STALE_TARGET',
  'CANDIDATE_NOT_FOUND',
  'CANDIDATE_NOT_READY',
  'PERMISSION_NEEDED',
  'PERMISSION_DENIED',
  'REMOTE_FETCH_BLOCKED',
  'REMOTE_FETCH_FAILED',
  'REMOTE_REDIRECT_PERMISSION_NEEDED',
  'SOURCE_TOO_LARGE',
  'RESULT_TOO_LARGE',
  'NOT_AN_IMAGE',
  'UNSUPPORTED_SOURCE_MIME',
  'UNSUPPORTED_RESULT_MIME',
  'SUSPECT_IMAGE_RESPONSE',
  'CANVAS_TAINTED',
  'CANVAS_EMPTY',
  'CAPTURE_AWAITING_FOCUS',
  'CAPTURE_THROTTLED',
  'CAPTURE_FAILED',
  'CAPTURE_EMPTY_INTERSECTION',
  'PRESENTATION_FAILED',
  'BINARY_NOT_FOUND',
  'BINARY_ACCESS_DENIED',
  'BINARY_STORE_FAILED',
  'JOB_NOT_FOUND',
  'JOB_STATE_CONFLICT',
  'PROCESSING_SPEC_INVALID',
  'HASH_FAILED',
  'ENGINE_HOST_PERMISSION_MISSING',
  'ENGINE_OFFLINE',
  'ENGINE_PAIRING_REQUIRED',
  'ENGINE_UNAUTHORIZED',
  'ENGINE_PROTOCOL_UNSUPPORTED',
  'ENGINE_CAPABILITY_MISSING',
  'ENGINE_PROFILE_NOT_FOUND',
  'ENGINE_PROFILE_NOT_READY',
  'ENGINE_PROFILE_CHANGED',
  'REMOTE_TRANSFER_CONSENT_REQUIRED',
  'ENGINE_IDEMPOTENCY_CONFLICT',
  'ENGINE_SOURCE_REJECTED',
  'ENGINE_JOB_NOT_FOUND',
  'ENGINE_JOB_INTERRUPTED',
  'ENGINE_JOB_CANCELLED',
  'ENGINE_RESULT_NOT_READY',
  'ENGINE_RESULT_INVALID',
  'ENGINE_REQUEST_FAILED',
  'RESULT_DIMENSIONS_MISMATCH',
  'DELIVERY_FAILED',
  'INTERNAL'
] as const;

export type AppErrorCode = (typeof ERROR_CODES)[number];

export type SerializedAppError = {
  code: AppErrorCode;
  message: string;
  retryable: boolean;
  details?: Record<string, string | number | boolean | null>;
};

export class AppError extends Error {
  readonly code: AppErrorCode;
  readonly retryable: boolean;
  readonly details?: Record<string, string | number | boolean | null>;

  constructor(
    code: AppErrorCode,
    message: string,
    options: {
      retryable?: boolean;
      details?: Record<string, string | number | boolean | null>;
      cause?: unknown;
    } = {}
  ) {
    super(message, { cause: options.cause });
    this.name = 'AppError';
    this.code = code;
    this.retryable = options.retryable ?? false;
    if (options.details !== undefined) this.details = options.details;
  }
}

export function serializeError(error: unknown): SerializedAppError {
  if (error instanceof AppError) {
    return {
      code: error.code,
      message: error.message,
      retryable: error.retryable,
      ...(error.details === undefined ? {} : { details: error.details })
    };
  }
  return {
    code: 'INTERNAL',
    message: error instanceof Error ? error.message : 'Unknown error',
    retryable: false
  };
}
