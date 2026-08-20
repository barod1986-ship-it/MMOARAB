import type { SerializedAppError } from '../core/errors.js';

export type Ok<T> = { ok: true; value: T };
export type Err = { ok: false; error: SerializedAppError };
export type Result<T> = Ok<T> | Err;

export const ok = <T>(value: T): Ok<T> => ({ ok: true, value });
export const err = (error: SerializedAppError): Err => ({ ok: false, error });
