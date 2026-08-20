import { browser } from 'wxt/browser';
import { AppError, type AppErrorCode } from '../core/errors.js';
import { MAX_RESULT_BYTES, MAX_SOURCE_BYTES } from '../shared/constants.js';
import { sha256Blob } from '../pipeline/sha256.js';
import { EngineConnectionStore } from './config-store.js';
import { RemoteTransferConsentStore, requiresRemoteTransferConsent } from '../ui/remote-transfer-consent.js';
import {
  ENGINE_BASE_URL,
  ENGINE_HOST_PATTERN,
  ENGINE_PROTOCOL_VERSION,
  type EngineCapabilities,
  type EngineConnectionSummary,
  type EngineCreateInput,
  type EngineCreateResponse,
  type EngineJobStatus,
  type EngineProfileDescriptor,
  type EngineResultPayload,
  type EngineModelCatalog,
  type EngineModelInstallStatus,
  type RemoteTransferConsentProof
} from './types.js';

const HEALTH_TIMEOUT_MS = 2_000;
const CAPABILITIES_TIMEOUT_MS = 5_000;
const CONTROL_TIMEOUT_MS = 5_000;
const TRANSFER_TIMEOUT_MS = 60_000;
const CAPABILITY_CACHE_MS = 30_000;

export class LocalProcessingGateway {
  readonly #store: EngineConnectionStore;
  readonly #remoteTransferConsent: RemoteTransferConsentStore;
  #cachedCapabilities: { expiresAt: number; value: EngineCapabilities } | null = null;

  constructor(store = new EngineConnectionStore(), remoteTransferConsent = new RemoteTransferConsentStore()) {
    this.#store = store;
    this.#remoteTransferConsent = remoteTransferConsent;
  }

  async hasHostPermission(): Promise<boolean> {
    return await browser.permissions.contains({ origins: [ENGINE_HOST_PATTERN] });
  }

  async getConnectionSummary(options: { probeAuthenticated?: boolean } = {}): Promise<EngineConnectionSummary> {
    const hostPermission = await this.hasHostPermission();
    const stored = await this.#store.get();
    const base: EngineConnectionSummary = { hostPermission, paired: Boolean(stored) };
    if (!hostPermission) return { ...base, errorCode: 'ENGINE_HOST_PERMISSION_MISSING' };
    if (!stored) return { ...base, errorCode: 'ENGINE_PAIRING_REQUIRED' };
    if (!options.probeAuthenticated) {
      return {
        ...base,
        ...(stored.engineVersion ? { engineVersion: stored.engineVersion } : {}),
        ...(stored.profileId ? { profileId: stored.profileId } : {}),
        ...(stored.profileFingerprint ? { profileFingerprint: stored.profileFingerprint } : {})
      };
    }
    try {
      const caps = await this.getCapabilities({ force: true });
      const profile = findProfile(caps, 'default-v1');
      return {
        ...base,
        reachable: true,
        protocolVersion: caps.protocolVersion,
        engineVersion: caps.engineVersion,
        profileId: profile.profileId,
        profileFingerprint: profile.profileFingerprint,
        profileState: profile.state
      };
    } catch (error) {
      const code = error instanceof AppError ? error.code : 'ENGINE_REQUEST_FAILED';
      return { ...base, reachable: false, errorCode: code };
    }
  }

  async probeHealth(): Promise<boolean> {
    if (!(await this.hasHostPermission())) throw new AppError('ENGINE_HOST_PERMISSION_MISSING', 'Loopback host permission has not been granted.');
    const response = await engineFetch('/healthz', { method: 'GET' }, HEALTH_TIMEOUT_MS, false);
    if (response.status !== 204) throw new AppError('ENGINE_REQUEST_FAILED', 'Local Engine health probe returned an unexpected status.');
    return true;
  }

  async pair(token: string): Promise<EngineConnectionSummary> {
    if (!(await this.hasHostPermission())) throw new AppError('ENGINE_HOST_PERMISSION_MISSING', 'Grant loopback host permission before pairing.');
    const normalized = token.trim();
    if (normalized.length < 20 || normalized.length > 512) throw new AppError('ENGINE_PAIRING_REQUIRED', 'Pairing token format is invalid.');
    const caps = await this.#fetchCapabilities(normalized);
    const profile = findProfile(caps, 'default-v1');
    await this.#store.save({ token: normalized, engineVersion: caps.engineVersion, profileId: profile.profileId, profileFingerprint: profile.profileFingerprint });
    this.#cachedCapabilities = { expiresAt: Date.now() + CAPABILITY_CACHE_MS, value: caps };
    return {
      hostPermission: true,
      paired: true,
      reachable: true,
      protocolVersion: caps.protocolVersion,
      engineVersion: caps.engineVersion,
      profileId: profile.profileId,
      profileFingerprint: profile.profileFingerprint,
      profileState: profile.state
    };
  }

  async disconnect(): Promise<void> {
    const stored = await this.#store.get();
    if (stored && await this.hasHostPermission()) {
      await engineFetch('/v1/pairing/reset', { method: 'POST', headers: authHeaders(stored.token) }, CONTROL_TIMEOUT_MS, true).catch(() => undefined);
    }
    this.#cachedCapabilities = null;
    await this.#store.clear();
  }

  async getCapabilities(options: { force?: boolean } = {}): Promise<EngineCapabilities> {
    if (!options.force && this.#cachedCapabilities && this.#cachedCapabilities.expiresAt > Date.now()) return this.#cachedCapabilities.value;
    const stored = await this.#requireConnection();
    const caps = await this.#fetchCapabilities(stored.token);
    const profile = findProfile(caps, 'default-v1');
    await this.#store.updateProfile({ engineVersion: caps.engineVersion, profileId: profile.profileId, profileFingerprint: profile.profileFingerprint });
    this.#cachedCapabilities = { expiresAt: Date.now() + CAPABILITY_CACHE_MS, value: caps };
    return caps;
  }

  async getModelCatalog(): Promise<EngineModelCatalog> {
    const stored = await this.#requireConnection();
    const response = await engineFetch('/v1/setup/models', { method: 'GET', headers: authHeaders(stored.token) }, CONTROL_TIMEOUT_MS, true);
    const payload = await readJson(response);
    if (!response.ok) throw engineResponseError(response.status, payload);
    return parseModelCatalog(payload);
  }

  async installModel(artifactId: string): Promise<EngineModelInstallStatus> {
    const stored = await this.#requireConnection();
    const response = await engineFetch(`/v1/setup/models/${encodeURIComponent(artifactId)}/install`, {
      method: 'POST', headers: authHeaders(stored.token)
    }, CONTROL_TIMEOUT_MS, true);
    const payload = await readJson(response);
    if (!response.ok) throw engineResponseError(response.status, payload);
    return parseModelInstallStatus(payload);
  }

  async getModelInstall(ticket: string): Promise<EngineModelInstallStatus> {
    const stored = await this.#requireConnection();
    const response = await engineFetch(`/v1/setup/model-installs/${encodeURIComponent(ticket)}`, { method: 'GET', headers: authHeaders(stored.token) }, CONTROL_TIMEOUT_MS, true);
    const payload = await readJson(response);
    if (!response.ok) throw engineResponseError(response.status, payload);
    return parseModelInstallStatus(payload);
  }

  async cancelModelInstall(ticket: string): Promise<EngineModelInstallStatus> {
    const stored = await this.#requireConnection();
    const response = await engineFetch(`/v1/setup/model-installs/${encodeURIComponent(ticket)}/cancel`, { method: 'POST', headers: authHeaders(stored.token) }, CONTROL_TIMEOUT_MS, true);
    const payload = await readJson(response);
    if (!response.ok) throw engineResponseError(response.status, payload);
    return parseModelInstallStatus(payload);
  }

  async getProfileFingerprint(profileId = 'default-v1'): Promise<string> {
    const caps = await this.getCapabilities();
    return requireReadyProfile(caps, profileId).profileFingerprint;
  }

  async refreshProfileFingerprint(profileId = 'default-v1'): Promise<string> {
    const caps = await this.getCapabilities({ force: true });
    return requireReadyProfile(caps, profileId).profileFingerprint;
  }

  async createJob(input: EngineCreateInput): Promise<EngineCreateResponse> {
    const stored = await this.#requireConnection();
    const remoteTransferConsent = await this.#consentProofForProfile(input.processingSpec.profileId, input.expectedProfileFingerprint);
    const body = {
      jobId: input.jobId,
      idempotencyKey: `sha256:${input.idempotencyKey}`,
      sourceSha256: `sha256:${input.sourceSha256}`,
      sourceBytes: input.sourceBytes,
      sourceMime: input.sourceMime,
      processingSpec: input.processingSpec,
      expectedProfileFingerprint: input.expectedProfileFingerprint,
      ...(remoteTransferConsent ? { remoteTransferConsent } : {})
    };
    const response = await engineFetch('/v1/jobs', {
      method: 'POST', headers: { ...authHeaders(stored.token), 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    }, CONTROL_TIMEOUT_MS, true);
    const payload = await readJson(response);
    if (!response.ok) throw engineResponseError(response.status, payload);
    const parsed = parseCreateResponse(payload);
    if (parsed.profileFingerprint !== input.expectedProfileFingerprint) throw new AppError('ENGINE_PROFILE_CHANGED', 'Engine returned a different profile fingerprint.');
    return parsed;
  }

  async uploadSource(input: { ticket: string; blob: Blob; sourceSha256: string; sourceMime: string }): Promise<void> {
    if (input.blob.size > MAX_SOURCE_BYTES) throw new AppError('SOURCE_TOO_LARGE', 'Source exceeds the Engine V1 byte limit.');
    const stored = await this.#requireConnection();
    const response = await engineFetch(`/v1/jobs/${encodeURIComponent(input.ticket)}/source`, {
      method: 'PUT',
      headers: {
        ...authHeaders(stored.token),
        'Content-Type': input.sourceMime,
        'X-Source-SHA256': `sha256:${input.sourceSha256}`
      },
      body: input.blob
    }, TRANSFER_TIMEOUT_MS, true);
    if (!response.ok) throw engineResponseError(response.status, await readJson(response));
  }

  async startJob(ticket: string, input: { profileId: string; expectedProfileFingerprint: string }): Promise<void> {
    const stored = await this.#requireConnection();
    const remoteTransferConsent = await this.#consentProofForProfile(input.profileId, input.expectedProfileFingerprint);
    const response = await engineFetch(`/v1/jobs/${encodeURIComponent(ticket)}/start`, {
      method: 'POST',
      headers: { ...authHeaders(stored.token), 'Content-Type': 'application/json' },
      body: JSON.stringify(remoteTransferConsent ? { remoteTransferConsent } : {})
    }, CONTROL_TIMEOUT_MS, true);
    if (!response.ok) throw engineResponseError(response.status, await readJson(response));
  }

  async getJob(ticket: string): Promise<EngineJobStatus> {
    const stored = await this.#requireConnection();
    const response = await engineFetch(`/v1/jobs/${encodeURIComponent(ticket)}`, { method: 'GET', headers: authHeaders(stored.token) }, CONTROL_TIMEOUT_MS, true);
    const payload = await readJson(response);
    if (!response.ok) throw engineResponseError(response.status, payload);
    return parseJobStatus(payload);
  }

  async cancelJob(ticket: string): Promise<void> {
    const stored = await this.#requireConnection();
    const response = await engineFetch(`/v1/jobs/${encodeURIComponent(ticket)}/cancel`, { method: 'POST', headers: authHeaders(stored.token) }, CONTROL_TIMEOUT_MS, true);
    if (!response.ok) throw engineResponseError(response.status, await readJson(response));
  }

  async releaseJob(ticket: string): Promise<void> {
    const stored = await this.#requireConnection();
    const response = await engineFetch(`/v1/jobs/${encodeURIComponent(ticket)}`, { method: 'DELETE', headers: authHeaders(stored.token) }, CONTROL_TIMEOUT_MS, true);
    if (!response.ok && response.status !== 404) throw engineResponseError(response.status, await readJson(response));
  }

  async fetchResult(input: { ticket: string; expectedProfileFingerprint: string; expectedWidth: number; expectedHeight: number }): Promise<EngineResultPayload> {
    const stored = await this.#requireConnection();
    const response = await engineFetch(`/v1/jobs/${encodeURIComponent(input.ticket)}/result`, { method: 'GET', headers: authHeaders(stored.token) }, TRANSFER_TIMEOUT_MS, true);
    if (!response.ok) throw engineResponseError(response.status, await readJson(response));
    const mime = normalizeResultMime(response.headers.get('content-type'));
    const declaredBytes = parsePositiveInteger(response.headers.get('content-length'), 'ENGINE_RESULT_INVALID');
    if (declaredBytes > MAX_RESULT_BYTES) throw new AppError('RESULT_TOO_LARGE', 'Engine result exceeds the V1 byte limit.');
    const declaredHash = response.headers.get('x-result-sha256');
    const width = parsePositiveInteger(response.headers.get('x-image-width'), 'ENGINE_RESULT_INVALID');
    const height = parsePositiveInteger(response.headers.get('x-image-height'), 'ENGINE_RESULT_INVALID');
    const profile = response.headers.get('x-profile-fingerprint');
    if (!declaredHash || !/^sha256:[a-f0-9]{64}$/.test(declaredHash)) throw new AppError('ENGINE_RESULT_INVALID', 'Engine result SHA-256 header is missing or malformed.');
    if (profile !== input.expectedProfileFingerprint) throw new AppError('ENGINE_PROFILE_CHANGED', 'Engine result profile fingerprint differs from the submitted work.');
    if (width !== input.expectedWidth || height !== input.expectedHeight) throw new AppError('RESULT_DIMENSIONS_MISMATCH', 'Engine result header dimensions do not match the source raster.');
    const blob = await readBoundedBlob(response, declaredBytes, mime);
    if (blob.size !== declaredBytes || blob.size > MAX_RESULT_BYTES) throw new AppError('ENGINE_RESULT_INVALID', 'Engine result byte count does not match its descriptor.');
    if (normalizeResultMime(blob.type) !== mime) throw new AppError('ENGINE_RESULT_INVALID', 'Engine result Blob MIME does not match its response header.');
    const actualHash = await sha256Blob(blob);
    if (`sha256:${actualHash}` !== declaredHash) throw new AppError('ENGINE_RESULT_INVALID', 'Engine result SHA-256 verification failed.');
    return {
      blob,
      mimeType: mime,
      byteLength: blob.size,
      sha256: actualHash,
      pixelWidth: width,
      pixelHeight: height,
      profileFingerprint: profile,
      encoderSemantics: 'engine-exact-lossless-v1'
    };
  }

  async #consentProofForProfile(profileId: string, expectedProfileFingerprint: string): Promise<RemoteTransferConsentProof | null> {
    const caps = await this.getCapabilities({ force: true });
    const profile = caps.profiles.find((candidate) => candidate.profileId === profileId);
    if (!profile) throw new AppError('ENGINE_PROFILE_NOT_FOUND', 'Selected Engine profile is not present in current capabilities.');
    if (profile.profileFingerprint !== expectedProfileFingerprint) {
      throw new AppError('ENGINE_PROFILE_CHANGED', 'Engine profile changed before remote-transfer authorization.');
    }
    if (profile.privacy.ocrTextLeavesDevice === null) {
      throw new AppError('ENGINE_PROFILE_NOT_READY', 'Engine profile has not frozen its OCR-text transfer behavior.');
    }
    if (!requiresRemoteTransferConsent(profile)) {
      if (profile.externalProviders.length !== 0) throw new AppError('ENGINE_PROTOCOL_UNSUPPORTED', 'Local-only Engine profile unexpectedly names external providers.');
      return null;
    }
    if (profile.externalProviders.length === 0) {
      throw new AppError('ENGINE_PROTOCOL_UNSUPPORTED', 'Remote-transfer Engine profile does not name its external provider.');
    }
    const proof = await this.#remoteTransferConsent.get(profile);
    if (!proof) {
      throw new AppError('REMOTE_TRANSFER_CONSENT_REQUIRED', 'Separate consent is required before extracted text can be sent to the selected external translation provider.');
    }
    return proof;
  }

  async #fetchCapabilities(token: string): Promise<EngineCapabilities> {
    const response = await engineFetch('/v1/capabilities', { method: 'GET', headers: authHeaders(token) }, CAPABILITIES_TIMEOUT_MS, true);
    const payload = await readJson(response);
    if (!response.ok) throw engineResponseError(response.status, payload);
    return validateCapabilities(payload);
  }

  async #requireConnection(): Promise<{ token: string }> {
    if (!(await this.hasHostPermission())) throw new AppError('ENGINE_HOST_PERMISSION_MISSING', 'Loopback host permission is required for the Local Engine.');
    const stored = await this.#store.get();
    if (!stored) throw new AppError('ENGINE_PAIRING_REQUIRED', 'Local Engine pairing is required.');
    return stored;
  }
}

function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

async function engineFetch(path: string, init: RequestInit, timeoutMs: number, authenticated: boolean): Promise<Response> {
  const url = new URL(path, ENGINE_BASE_URL);
  if (url.origin !== ENGINE_BASE_URL) throw new AppError('ENGINE_REQUEST_FAILED', 'Engine request escaped the fixed loopback origin.');
  try {
    return await fetch(url, { ...init, redirect: 'error', cache: 'no-store', signal: AbortSignal.timeout(timeoutMs) });
  } catch (cause) {
    if (cause instanceof AppError) throw cause;
    throw new AppError(authenticated ? 'ENGINE_OFFLINE' : 'ENGINE_REQUEST_FAILED', 'Local Engine request could not reach the fixed loopback endpoint.', { retryable: true, cause });
  }
}

function validateCapabilities(value: unknown): EngineCapabilities {
  if (!isRecord(value)) throw new AppError('ENGINE_PROTOCOL_UNSUPPORTED', 'Engine capabilities response is not an object.');
  if (value.protocolVersion !== ENGINE_PROTOCOL_VERSION) throw new AppError('ENGINE_PROTOCOL_UNSUPPORTED', 'Local Engine protocol version is not supported.');
  if (typeof value.engineVersion !== 'string' || !value.engineVersion) throw new AppError('ENGINE_PROTOCOL_UNSUPPORTED', 'Engine version is missing from capabilities.');
  if (!isPositiveInteger(value.maxSourceBytes) || value.maxSourceBytes < MAX_SOURCE_BYTES) throw new AppError('ENGINE_CAPABILITY_MISSING', 'Engine source-byte capability is below the V1 contract.');
  if (!isPositiveInteger(value.maxResultBytes) || value.maxResultBytes < MAX_RESULT_BYTES) throw new AppError('ENGINE_CAPABILITY_MISSING', 'Engine result-byte capability is below the V1 contract.');
  if (!stringArray(value.supportedOutputKinds).includes('translated-raster-image')) throw new AppError('ENGINE_CAPABILITY_MISSING', 'Engine does not support translated raster output.');
  if (!numberArray(value.resultManifestSchemaVersions).includes(1)) throw new AppError('ENGINE_CAPABILITY_MISSING', 'Engine does not support result manifest schema V1.');
  if (!stringArray(value.supportedTargetLanguages).includes('ar')) throw new AppError('ENGINE_CAPABILITY_MISSING', 'Engine does not support Arabic output.');
  if (!Array.isArray(value.profiles)) throw new AppError('ENGINE_CAPABILITY_MISSING', 'Engine profile descriptors are missing.');
  const profiles: EngineProfileDescriptor[] = value.profiles.map(parseProfile);
  return {
    protocolVersion: 1,
    engineVersion: value.engineVersion,
    maxSourceBytes: value.maxSourceBytes,
    maxResultBytes: value.maxResultBytes,
    supportedOutputKinds: stringArray(value.supportedOutputKinds),
    resultManifestSchemaVersions: numberArray(value.resultManifestSchemaVersions),
    supportedSourceLanguages: stringArray(value.supportedSourceLanguages),
    supportedTargetLanguages: stringArray(value.supportedTargetLanguages),
    recommendedDefaults: stringRecord(value.recommendedDefaults),
    hardware: parseHardware(value.hardware),
    recommendedConcurrency: isPositiveInteger(value.recommendedConcurrency) ? value.recommendedConcurrency : 1,
    profiles
  };
}

function findProfile(caps: EngineCapabilities, profileId: string): EngineProfileDescriptor {
  const profile = caps.profiles.find((candidate) => candidate.profileId === profileId);
  if (!profile) throw new AppError('ENGINE_PROFILE_NOT_FOUND', `Engine profile ${profileId} is unavailable.`);
  if (!/^sha256:[a-f0-9]{64}$/.test(profile.profileFingerprint)) throw new AppError('ENGINE_PROTOCOL_UNSUPPORTED', 'Engine profile fingerprint is malformed.');
  return profile;
}

function requireReadyProfile(caps: EngineCapabilities, profileId: string): EngineProfileDescriptor {
  const profile = findProfile(caps, profileId);
  if (profile.state !== 'ready') throw new AppError('ENGINE_PROFILE_NOT_READY', `Engine profile ${profileId} is not ready.`, { details: { state: profile.state } });
  return profile;
}

function parseModelCatalog(value: unknown): EngineModelCatalog {
  if (!isRecord(value) || value.schemaVersion !== 1 || typeof value.catalogRevision !== 'string' || !Array.isArray(value.artifacts)) {
    throw new AppError('ENGINE_PROTOCOL_UNSUPPORTED', 'Engine model catalog is malformed.');
  }
  const artifacts = value.artifacts.map((item) => {
    if (!isRecord(item) || typeof item.artifactId !== 'string' || typeof item.revision !== 'string' ||
        typeof item.expectedFilename !== 'string' || !isPositiveInteger(item.bytes) || typeof item.sha256 !== 'string' ||
        !/^sha256:[a-f0-9]{64}$/.test(item.sha256) || typeof item.licenseSpdx !== 'string' ||
        (item.redistribution !== 'approved' && item.redistribution !== 'download-only') ||
        !isModelInstallState(item.state) || !isNonNegativeInteger(item.downloadedBytes)) {
      throw new AppError('ENGINE_PROTOCOL_UNSUPPORTED', 'Engine model artifact descriptor is malformed.');
    }
    if (item.downloadedBytes > item.bytes) throw new AppError('ENGINE_PROTOCOL_UNSUPPORTED', 'Engine model download progress exceeds its pinned size.');
    return {
      artifactId: item.artifactId, revision: item.revision, expectedFilename: item.expectedFilename, bytes: item.bytes,
      sha256: item.sha256, licenseSpdx: item.licenseSpdx, redistribution: item.redistribution, state: item.state,
      downloadedBytes: item.downloadedBytes,
      ...(typeof item.ticket === 'string' ? { ticket: item.ticket } : {}),
      ...(isRecord(item.error) && typeof item.error.code === 'string' && typeof item.error.message === 'string' ? { error: { code: item.error.code, message: item.error.message } } : {})
    };
  });
  return { schemaVersion: 1, catalogRevision: value.catalogRevision, artifacts };
}

function parseModelInstallStatus(value: unknown): EngineModelInstallStatus {
  if (!isRecord(value) || typeof value.artifactId !== 'string' || !isModelInstallState(value.state) || value.state === 'missing' ||
      !isNonNegativeInteger(value.downloadedBytes) || !isPositiveInteger(value.totalBytes) || value.downloadedBytes > value.totalBytes) {
    throw new AppError('ENGINE_PROTOCOL_UNSUPPORTED', 'Engine model install status is malformed.');
  }
  return {
    ...(typeof value.ticket === 'string' ? { ticket: value.ticket } : {}),
    artifactId: value.artifactId, state: value.state, downloadedBytes: value.downloadedBytes, totalBytes: value.totalBytes,
    ...(typeof value.cancelRequested === 'boolean' ? { cancelRequested: value.cancelRequested } : {}),
    ...(isRecord(value.error) && typeof value.error.code === 'string' && typeof value.error.message === 'string' ? { error: { code: value.error.code, message: value.error.message } } : {})
  };
}

function parseCreateResponse(value: unknown): EngineCreateResponse {
  if (!isRecord(value) || typeof value.engineTicket !== 'string' || value.engineTicket.length < 8 || typeof value.state !== 'string' || typeof value.profileFingerprint !== 'string') {
    throw new AppError('ENGINE_PROTOCOL_UNSUPPORTED', 'Engine create-job response is malformed.');
  }
  if (!isEngineState(value.state)) throw new AppError('ENGINE_PROTOCOL_UNSUPPORTED', 'Engine create-job state is unsupported.');
  return { engineTicket: value.engineTicket, state: value.state, profileFingerprint: value.profileFingerprint, ...(value.result ? { result: parseResultDescriptor(value.result) } : {}) };
}

function parseJobStatus(value: unknown): EngineJobStatus {
  if (!isRecord(value) || typeof value.state !== 'string' || value.state === 'completed' || !isEngineState(value.state) || typeof value.updatedAt !== 'string') {
    throw new AppError('ENGINE_PROTOCOL_UNSUPPORTED', 'Engine job-status response is malformed.');
  }
  return {
    state: value.state as EngineJobStatus['state'],
    updatedAt: value.updatedAt,
    ...(typeof value.stage === 'string' ? { stage: value.stage } : {}),
    ...(isRecord(value.progress) && isNonNegativeInteger(value.progress.completed) && isPositiveInteger(value.progress.total) ? { progress: { completed: value.progress.completed, total: value.progress.total } } : {}),
    ...(isRecord(value.error) ? { error: { ...(typeof value.error.code === 'string' ? { code: value.error.code } : {}), ...(typeof value.error.message === 'string' ? { message: value.error.message } : {}), ...(typeof value.error.retryable === 'boolean' ? { retryable: value.error.retryable } : {}) } } : {}),
    ...(value.result ? { result: parseResultDescriptor(value.result) } : {})
  };
}

function parseResultDescriptor(value: unknown) {
  if (!isRecord(value) || (value.mime !== 'image/webp' && value.mime !== 'image/png') || !isPositiveInteger(value.bytes) || typeof value.sha256 !== 'string' || !/^sha256:[a-f0-9]{64}$/.test(value.sha256) || !isPositiveInteger(value.width) || !isPositiveInteger(value.height) || typeof value.manifestAvailable !== 'boolean') {
    throw new AppError('ENGINE_PROTOCOL_UNSUPPORTED', 'Engine result descriptor is malformed.');
  }
  return { mime: value.mime, bytes: value.bytes, sha256: value.sha256, width: value.width, height: value.height, manifestAvailable: value.manifestAvailable } as const;
}

function parseProfile(value: unknown): EngineProfileDescriptor {
  if (!isRecord(value) || typeof value.profileId !== 'string' || typeof value.profileFingerprint !== 'string' || !isProfileState(value.state)) {
    throw new AppError('ENGINE_PROTOCOL_UNSUPPORTED', 'Engine profile descriptor is malformed.');
  }
  if (!isRecord(value.privacy) || typeof value.privacy.imageLeavesDevice !== 'boolean' ||
      (typeof value.privacy.ocrTextLeavesDevice !== 'boolean' && value.privacy.ocrTextLeavesDevice !== null) ||
      typeof value.privacy.visualContextLeavesDevice !== 'boolean') {
    throw new AppError('ENGINE_PROTOCOL_UNSUPPORTED', 'Engine profile privacy descriptor is malformed.');
  }
  const externalProviders = stringArray(value.externalProviders);
  const remote = value.privacy.imageLeavesDevice === true || value.privacy.ocrTextLeavesDevice === true || value.privacy.visualContextLeavesDevice === true;
  if ((remote && externalProviders.length === 0) || (!remote && externalProviders.length !== 0)) {
    throw new AppError('ENGINE_PROTOCOL_UNSUPPORTED', 'Engine profile external-provider disclosure does not match its privacy descriptor.');
  }
  return {
    profileId: value.profileId,
    profileFingerprint: value.profileFingerprint,
    state: value.state,
    privacy: {
      imageLeavesDevice: value.privacy.imageLeavesDevice,
      ocrTextLeavesDevice: value.privacy.ocrTextLeavesDevice,
      visualContextLeavesDevice: value.privacy.visualContextLeavesDevice
    },
    externalProviders
  };
}

function parseHardware(value: unknown): EngineCapabilities['hardware'] {
  if (!isRecord(value)) return { cpu: true, cuda: false, rocm: false, metal: false, vulkan: false };
  return { cpu: value.cpu === true, cuda: value.cuda === true, rocm: value.rocm === true, metal: value.metal === true, vulkan: value.vulkan === true };
}

function engineResponseError(status: number, payload: unknown): AppError {
  let engineCode = '';
  let message = `Local Engine request failed with HTTP ${status}.`;
  let retryable = status >= 500;
  if (isRecord(payload) && isRecord(payload.error)) {
    if (typeof payload.error.code === 'string') engineCode = payload.error.code;
    if (typeof payload.error.message === 'string') message = payload.error.message;
    if (typeof payload.error.retryable === 'boolean') retryable = payload.error.retryable;
  }
  const map: Record<string, AppErrorCode> = {
    unauthorized: 'ENGINE_UNAUTHORIZED',
    profile_not_found: 'ENGINE_PROFILE_NOT_FOUND',
    profile_not_ready: 'ENGINE_PROFILE_NOT_READY',
    profile_changed: 'ENGINE_PROFILE_CHANGED',
    remote_transfer_consent_required: 'REMOTE_TRANSFER_CONSENT_REQUIRED',
    idempotency_conflict: 'ENGINE_IDEMPOTENCY_CONFLICT',
    source_too_large: 'SOURCE_TOO_LARGE',
    result_too_large: 'RESULT_TOO_LARGE',
    source_hash_mismatch: 'ENGINE_SOURCE_REJECTED',
    invalid_source: 'ENGINE_SOURCE_REJECTED',
    job_not_found: 'ENGINE_JOB_NOT_FOUND',
    result_not_ready: 'ENGINE_RESULT_NOT_READY',
    job_cancelled: 'ENGINE_JOB_CANCELLED',
    job_interrupted: 'ENGINE_JOB_INTERRUPTED'
  };
  return new AppError(map[engineCode] ?? (status === 401 ? 'ENGINE_UNAUTHORIZED' : 'ENGINE_REQUEST_FAILED'), message, { retryable, ...(engineCode ? { details: { engineCode } } : {}) });
}

async function readBoundedBlob(response: Response, declaredBytes: number, mime: 'image/webp' | 'image/png'): Promise<Blob> {
  if (!response.body) throw new AppError('ENGINE_RESULT_INVALID', 'Engine result response has no readable body.');
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!value) continue;
      total += value.byteLength;
      if (total > MAX_RESULT_BYTES || total > declaredBytes) {
        await reader.cancel().catch(() => undefined);
        throw new AppError('RESULT_TOO_LARGE', 'Engine result stream exceeded its declared or V1 byte limit.');
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  if (total !== declaredBytes) throw new AppError('ENGINE_RESULT_INVALID', 'Engine result stream length does not match Content-Length.');
  return new Blob(chunks, { type: mime });
}

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return {};
  try { return JSON.parse(text) as unknown; } catch { throw new AppError('ENGINE_PROTOCOL_UNSUPPORTED', 'Engine returned malformed JSON.'); }
}

function normalizeResultMime(value: string | null): 'image/webp' | 'image/png' {
  const mime = value?.split(';', 1)[0]?.trim().toLowerCase();
  if (mime === 'image/webp' || mime === 'image/png') return mime;
  throw new AppError('UNSUPPORTED_RESULT_MIME', 'Engine result Content-Type is not allowed in V1.');
}

function parsePositiveInteger(value: string | null, code: AppErrorCode): number {
  if (!value || !/^[0-9]+$/.test(value)) throw new AppError(code, 'Engine result numeric header is missing or malformed.');
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed <= 0) throw new AppError(code, 'Engine result numeric header is outside the safe range.');
  return parsed;
}

function isEngineState(value: string): value is EngineCreateResponse['state'] {
  return ['awaiting_source', 'queued', 'running', 'succeeded', 'completed', 'failed', 'cancel_requested', 'cancelled', 'interrupted'].includes(value);
}
function isProfileState(value: unknown): value is EngineProfileDescriptor['state'] {
  return typeof value === 'string' && ['ready', 'needs-download', 'unavailable-hardware', 'misconfigured-provider', 'renderer-missing', 'runtime-unavailable'].includes(value);
}
function isModelInstallState(value: unknown): value is import('./types.js').EngineModelInstallState { return typeof value === 'string' && ['missing', 'queued', 'running', 'ready', 'succeeded', 'failed', 'cancelled'].includes(value); }
function isRecord(value: unknown): value is Record<string, any> { return typeof value === 'object' && value !== null && !Array.isArray(value); }
function isPositiveInteger(value: unknown): value is number { return typeof value === 'number' && Number.isSafeInteger(value) && value > 0; }
function isNonNegativeInteger(value: unknown): value is number { return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0; }
function stringArray(value: unknown): string[] { return Array.isArray(value) && value.every((item) => typeof item === 'string') ? [...value] : []; }
function numberArray(value: unknown): number[] { return Array.isArray(value) && value.every((item) => typeof item === 'number' && Number.isSafeInteger(item)) ? [...value] : []; }
function stringRecord(value: unknown): Record<string, string> { if (!isRecord(value)) return {}; const out: Record<string, string> = {}; for (const [key, item] of Object.entries(value)) if (typeof item === 'string') out[key] = item; return out; }

