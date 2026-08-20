import { access, readFile } from 'node:fs/promises';

const root = new URL('../', import.meta.url);
async function text(path) { return await readFile(new URL(path, root), 'utf8'); }
async function exists(path) { try { await access(new URL(path, root)); return true; } catch { return false; } }

const files = {
  manifest: await text('wxt.config.ts'),
  ci: `${await text('.github/workflows/ci-extension.yml')}\n${await text('.github/workflows/ci-engine.yml')}`, 
  package: JSON.parse(await text('package.json')),
  constants: await text('src/shared/constants.ts'),
  gateway: await text('src/engine/local-processing-gateway.ts'),
  engineTypes: await text('src/engine/types.ts'),
  engineStore: await text('src/engine/config-store.ts'),
  coordinator: await text('src/pipeline/coordinator.ts'),
  backgroundHandlers: await text('src/messaging/background-handlers.ts'),
  messaging: await text('src/messaging/protocol.ts'),
  sourceValidation: await text('src/pipeline/source-validation.ts'),
  workStore: await text('src/queue/work-store.ts'),
  retry: await text('src/queue/retry-wake.ts'),
  pyproject: await text('engine/pyproject.toml'),
  engineConstants: await text('engine/mte_engine/constants.py'),
  engineConfig: await text('engine/mte_engine/config.py'),
  engineApp: await text('engine/mte_engine/app.py'),
  engineSecurity: await text('engine/mte_engine/security.py'),
  engineModels: await text('engine/mte_engine/models.py'),
  engineDb: await text('engine/mte_engine/db.py'),
  engineSpool: await text('engine/mte_engine/spool.py'),
  engineProcessor: await text('engine/mte_engine/processor.py'),
  engineStaged: await text('engine/mte_engine/pipeline/staged.py'),
  engineProfile: await text('engine/mte_engine/profile.py'),
  engineService: await text('engine/mte_engine/service.py'),
  engineMain: await text('engine/mte_engine/__main__.py'),
  engineProtocolTests: await text('engine/tests/test_protocol.py'),
  engineStaticTests: await text('engine/tests/test_security_static.py')
};

const extensionJoined = [files.gateway, files.engineTypes, files.engineStore, files.coordinator, files.backgroundHandlers, files.messaging].join('\n');
const engineJoined = [files.engineConfig, files.engineApp, files.engineSecurity, files.engineModels, files.engineDb, files.engineSpool, files.engineProcessor, files.engineService, files.engineMain].join('\n');

const checks = [
  ['manifest remains at or beyond Phase 4 and keeps Chrome 148 baseline', /version:\s*'0\.(?:[5-9]|[1-9][0-9]+)\./.test(files.manifest) && files.manifest.includes("minimum_chrome_version: '148'")],
  ['loopback permission is optional and literal', files.manifest.includes("'http://127.0.0.1/*'") && !files.manifest.includes("http://localhost/*")],
  ['extension Engine origin is fixed to literal loopback port 17891', files.engineTypes.includes("ENGINE_BASE_URL = 'http://127.0.0.1:17891'")],
  ['Engine client refuses redirects', files.gateway.includes("redirect: 'error'")],
  ['health, capabilities, control and transfer timeouts match V1', files.gateway.includes('HEALTH_TIMEOUT_MS = 2_000') && files.gateway.includes('CAPABILITIES_TIMEOUT_MS = 5_000') && files.gateway.includes('CONTROL_TIMEOUT_MS = 5_000') && files.gateway.includes('TRANSFER_TIMEOUT_MS = 60_000')],
  ['Bearer token is stored only in trusted extension storage path', files.engineStore.includes("storage.local") && files.backgroundHandlers.includes('trustedExtensionPageSender') && files.backgroundHandlers.includes("onMessage('engine:pair'")],
  ['content-script protocol has no Engine token getter', !files.messaging.includes('engine:get-token') && !files.messaging.includes('engine:token')],
  ['result stream is bounded before Blob construction', files.gateway.includes('readBoundedBlob') && files.gateway.includes('total > MAX_RESULT_BYTES') && files.gateway.includes('total > declaredBytes')],
  ['result verification checks hash, MIME, dimensions and profile', files.gateway.includes('sha256Blob(blob)') && files.gateway.includes('ENGINE_PROFILE_CHANGED') && files.gateway.includes('RESULT_DIMENSIONS_MISMATCH') && files.gateway.includes('normalizeResultMime(blob.type)')],
  ['ProcessingSpec/SFX exact-lossless contract survives Engine handoff', files.sourceValidation.includes("'engine-exact-lossless-v1'") && files.coordinator.includes('processingSpec: current.processingSpec!')],
  ['durable Engine ticket is persisted immediately after idempotent create', files.coordinator.includes('draft.engineTicket = durableTicket') && files.coordinator.includes('idempotencyKey: current.jobSignature')],
  ['interrupted Engine jobs restart on the same ticket', files.coordinator.includes("status.state === 'interrupted'") && files.coordinator.includes('await this.#gateway.startJob(ticket)')],
  ['profile changes rebuild Work identity instead of reusing stale signature', files.coordinator.includes('#migrateWorkToCurrentProfile') && files.coordinator.includes('refreshProfileFingerprint') && files.coordinator.includes('deriveWorkSignature') && files.coordinator.includes("draft.stage = 'waiting-work'")],
  ['long Engine rechecks persist through shared queue alarm, not long timers', files.constants.includes('ENGINE_DURABLE_RECHECK_MS = 30_000') && files.retry.includes('browser.alarms') && files.constants.includes("QUEUE_WAKE_ALARM = 'queue-wake'")],
  ['only short bounded polling uses an in-memory delay', files.constants.includes('ENGINE_POLL_GRACE_MS = 4_000') && files.constants.includes('ENGINE_POLL_INTERVAL_MS = 250') && files.coordinator.includes('await delay(ENGINE_POLL_INTERVAL_MS)')],
  ['old mock gateway is removed', !(await exists('src/pipeline/mock-gateway.ts')) && !extensionJoined.includes('MockProcessingGateway')],
  ['Phase 4 CI gates both extension and pinned Python Engine', files.ci.includes('name: ci-extension') && files.ci.includes('name: ci-engine') && files.ci.includes('package-lock.json') && files.ci.includes('engine/uv.lock') && files.ci.includes('uv sync --locked --extra test') && files.ci.includes("python: ['3.11', '3.13']")],
  ['Python Engine requires 3.11+ and pinned protocol-shell dependencies', files.pyproject.includes('requires-python = ">=3.11"') && files.pyproject.includes('fastapi==0.141.1') && files.pyproject.includes('pydantic==2.13.4') && files.pyproject.includes('uvicorn==0.52.3') && files.pyproject.includes('pillow==12.3.0')],
  ['Engine constants freeze loopback/port/32MiB/120MP/24h', files.engineConstants.includes('DEFAULT_HOST = "127.0.0.1"') && files.engineConstants.includes('DEFAULT_PORT = 17891') && files.engineConstants.includes('32 * 1024 * 1024') && files.engineConstants.includes('MAX_DECODED_PIXELS = 120_000_000') && files.engineConstants.includes('SPOOL_TTL_SECONDS = 24 * 60 * 60')],
  ['Engine refuses non-loopback bind and non-default port configuration', files.engineConfig.includes('if host != DEFAULT_HOST') && files.engineConfig.includes('port != DEFAULT_PORT') && files.engineConfig.includes('must bind only to 127.0.0.1') && files.engineProtocolTests.includes('MTE_ENGINE_PORT')],
  ['opaque pairing secret uses cryptographic 32-byte entropy and rotates on reset', files.engineConfig.includes('secrets.token_urlsafe(32)') && files.engineConfig.includes('rotate_token: bool = True')],
  ['paired origin is exact chrome-extension origin', files.engineConfig.includes('chrome-extension://[a-p]{32}') && files.engineSecurity.includes('is_valid_extension_origin') && files.engineSecurity.includes('hmac.compare_digest')],
  ['Host and peer validation protect every request', files.engineApp.includes('peer_is_loopback(request.client.host)') && files.engineApp.includes('request.headers.get("host") != settings.expected_host_header')],
  ['Engine authenticates sensitive routes in middleware before body parsing', files.engineApp.includes('if request.url.path.startswith("/v1/")') && files.engineApp.includes('authenticate_request(request, pairing, allow_pairing=request.url.path == "/v1/capabilities")') && files.engineProtocolTests.includes('unauthenticated_malformed')],
  ['forwarded proxy headers are disabled', files.engineMain.includes('proxy_headers=False') && files.engineMain.includes('forwarded_allow_ips=""')],
  ['production docs/OpenAPI endpoints are disabled', files.engineApp.includes('docs_url=None') && files.engineApp.includes('redoc_url=None') && files.engineApp.includes('openapi_url=None')],
  ['job create schema is strict/extra-forbid and has no URL/path fields', files.engineModels.includes('extra="forbid", strict=True') && !files.engineModels.includes('imageUrl') && !files.engineModels.includes('sourceUrl') && !files.engineModels.includes('filesystemPath')],
  ['JSON translatableKinds uses list semantics under strict Pydantic', files.engineModels.includes('translatableKinds: list[Literal["dialogue", "narration"]]') && files.engineModels.includes('value != ["dialogue", "narration"]')],
  ['SQLite dedupe key is profile fingerprint + idempotency key', files.engineDb.includes('UNIQUE(profile_fingerprint, idempotency_key)') && files.engineDb.includes('request_fingerprint')],
  ['running jobs recover to interrupted and can requeue same ticket', files.engineDb.includes("state='interrupted'") && files.engineDb.includes('if state == "interrupted" and row["source_path"]')],
  ['retryable Engine failures persist in SQLite status metadata', files.engineDb.includes('error_retryable INTEGER NOT NULL DEFAULT 0') && files.engineService.includes('retryable=exc.retryable') && files.engineApp.includes('bool(row.get("error_retryable"))')],
  ['source upload is streamed, hashed, size bounded, temp-written and atomically renamed', files.engineSpool.includes('async for chunk in request.stream()') && files.engineSpool.includes('hashlib.sha256()') && files.engineSpool.includes('MAX_SOURCE_BYTES') && files.engineSpool.includes('tempfile.mkstemp') && files.engineSpool.includes('os.replace')],
  ['existing source shortcut revalidates bytes and hash before idempotent reuse', files.engineSpool.includes('def verify_file') && files.engineApp.includes('spool.verify_file(existing') && files.engineProtocolTests.includes('tampered_source_path')],
  ['source/result spool filenames derive only from server-issued ticket', files.engineSpool.includes('f"{ticket}.bin"') && files.engineSpool.includes('f"{ticket}{suffix}"')],
  ['local Engine data/spool artifacts use restrictive permissions where supported', files.engineConfig.includes('os.chmod(self._data_dir, 0o700)') && files.engineSpool.includes('os.chmod(directory, 0o700)') && files.engineProcessor.includes('0o600') && files.engineDb.includes('os.chmod(candidate, 0o600)') && files.engineProtocolTests.includes('stat.S_IMODE')],
  ['processor enforces one-frame/120MP exact-lossless WebP then PNG rescue', files.engineStaged.includes('n_frames') && files.engineStaged.includes('MAX_DECODED_PIXELS') && files.engineStaged.includes('lossless=True') && files.engineStaged.includes('_encode_exact_lossless') && files.engineStaged.includes('_has_pixel_difference')],
  ['processor preserves dimensions and strips arbitrary metadata by re-encoding normalized RGBA', files.engineStaged.includes('ImageOps.exif_transpose(source).convert("RGBA")') && files.engineStaged.includes('exif=b""') && files.engineStaged.includes('xmp=b""')],
  ['profile fingerprint includes concrete image codec versions that affect raster semantics', files.engineProfile.includes('imageCodecVersions') && files.engineProfile.includes('_feature_version("webp")') && files.engineProfile.includes('_feature_version("zlib")') && files.engineProfile.includes('_feature_version("libjpeg_turbo")') && files.engineProfile.includes('_feature_version("avif")')],
  ['Engine has no outbound URL-fetch client or unsafe dynamic deserialization path', files.engineStaticTests.includes('test_translation_job_path_has_no_url_fetch_client_dependency') && files.engineStaticTests.includes('test_only_model_installer_owns_network_download_client') && files.engineStaticTests.includes('test_no_unsafe_deserialization_or_dynamic_execution')],
  ['pairing reset response remains CORS-readable using pre-call allow decision', files.engineApp.includes('cors_allowed = bool(origin and _cors_origin_allowed')],
  ['CORS preflight is restricted to paired/initial-capabilities extension origin and known headers', files.engineApp.includes('_preflight_response') && files.engineApp.includes('allowed_headers = {"authorization", "content-type", "x-source-sha256"}') && files.engineProtocolTests.includes('paired_preflight') && files.engineProtocolTests.includes('other_preflight')],
  ['Phase 4 invariants survive in later packages', /^0\.(?:[5-9]|[1-9][0-9]+)\./.test(files.package.version)]
];

let failed = false;
for (const [name, ok] of checks) {
  console.log(`${ok ? 'ok' : 'not ok'} - ${name}`);
  if (!ok) failed = true;
}
console.log(`# ${checks.length} Phase 4 contract checks`);
if (failed) process.exitCode = 1;
