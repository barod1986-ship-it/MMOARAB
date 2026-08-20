import { readFileSync, readdirSync, statSync } from 'node:fs';
import { resolve, relative, extname } from 'node:path';

const root = resolve('.');
let passed = 0;
const check = (condition, label) => { if (!condition) throw new Error(`Phase 7 contract failed: ${label}`); passed++; };
const text = (path) => readFileSync(resolve(root, path), 'utf8');
const json = (path) => JSON.parse(text(path));

const pkg = json('package.json');
check(['0.7.0-phase7', '0.8.0-phase8', '0.9.0-phase9', '0.10.0-v1candidate'].includes(pkg.version), 'extension version is Phase 7 or a later compatible phase');
check(pkg.scripts?.['check:phase7-contracts'] === 'node scripts/verify-phase7-contracts.mjs', 'Phase 7 verifier is scripted');
const pyproject = text('engine/pyproject.toml');
check(pyproject.includes('version = "0.5.0"'), 'Engine version is Phase 7');
check(pyproject.includes('pyinstaller==6.22.2'), 'PyInstaller is exactly pinned');
check(pyproject.includes('"mte_engine.resources" = ["*.json"]'), 'distribution catalog is package data');
const versions = json('engine/packaging/runtime-versions.json');
check(versions.python === '3.13.15' && versions.uv === '0.12.5' && versions.pyinstaller === '6.22.2', 'release runtime versions are exact');
check(versions.protocolMajor === 1 && versions.engineVersion === '0.5.0', 'compatibility versions are explicit');

const catalog = json('engine/model-catalog/model-distribution-v1.json');
const bundledCatalog = json('engine/mte_engine/resources/model-distribution-v1.json');
check(JSON.stringify(catalog) === JSON.stringify(bundledCatalog), 'bundled model catalog exactly matches reviewed source catalog');
check(catalog.schemaVersion === 1 && Array.isArray(catalog.allowedHosts) && Array.isArray(catalog.artifacts), 'distribution catalog schema is fixed');
check(catalog.artifacts.length === 0, 'unfrozen Gate D publishes no invented model downloads');
const installer = text('engine/mte_engine/model_install.py');
for (const token of ['https', 'allowed_hosts', 'Range', 'Content-Range', '.part', 'os.replace', '_hash_file', 'sha256', 'download-only', 'ipaddress.ip_address']) {
  check(installer.includes(token), `model installer enforces ${token}`);
}
check(installer.includes('V1 installs exact file artifacts only'), 'archive extraction is not silently trusted in V1');
const app = text('engine/mte_engine/app.py');
for (const route of ['/v1/setup/models', '/v1/setup/models/{artifact_id}/install', '/v1/setup/model-installs/{ticket}', '/v1/setup/model-installs/{ticket}/cancel']) check(app.includes(route), `Engine exposes ${route}`);
const protocol = text('src/messaging/protocol.ts');
for (const message of ['ui:get-model-catalog', 'ui:install-model', 'ui:get-model-install', 'ui:cancel-model-install']) check(protocol.includes(message), `trusted UI protocol includes ${message}`);
const handlers = text('src/messaging/background-handlers.ts');
for (const message of ['ui:get-model-catalog', 'ui:install-model', 'ui:get-model-install', 'ui:cancel-model-install']) {
  const position = handlers.indexOf(`onMessage('${message}'`);
  check(position >= 0 && handlers.slice(position, position + 220).includes('requireTrustedUiSender'), `${message} is restricted to extension UI`);
}
const options = text('src/entrypoints/options/main.tsx');
check(options.includes('modelCatalog.artifacts.length === 0') && options.includes("t('modelCatalogEmpty')"), 'Options fail closed when no production model catalog exists');
check(options.includes("sendMessage('ui:install-model'") && options.includes("sendMessage('ui:cancel-model-install'"), 'Options owns explicit install/cancel controls');

const claims = json('engine/packaging/support-claims.json');
check(claims.targets.length === 3, 'support matrix has three explicit candidate targets');
for (const target of claims.targets) check(target.publicSupportClaimed === false, `${target.id} does not make an unverified public support claim`);
check(claims.targets.find((x) => x.id === 'windows-x86_64')?.requiredGates.includes('authenticode'), 'Windows public gate requires Authenticode');
const macGates = claims.targets.find((x) => x.id === 'macos-arm64')?.requiredGates ?? [];
check(macGates.includes('developer-id') && macGates.includes('notarization') && macGates.includes('stapling'), 'macOS public gate requires Developer ID/notarization/stapling');
check(claims.targets.find((x) => x.id === 'linux-x86_64')?.status === 'developer-preview', 'Linux is not overclaimed as official support');

const metadata = text('engine/scripts/release_metadata.py');
check(metadata.includes("uv.lock is missing") && metadata.includes("--format', 'cyclonedx1.5") && metadata.includes("--format', 'pylock.toml"), 'Engine metadata requires lock and exports CycloneDX/pylock');
check(metadata.includes("bomFormat") && metadata.includes("specVersion") && metadata.includes("components"), 'preview CycloneDX output is schema-sanity checked');
const extMetadata = text('scripts/release-extension-metadata.mjs');
check(extMetadata.includes('package-lock.json') && extMetadata.includes('npm') && extMetadata.includes('CycloneDX'), 'extension metadata requires npm lock and CycloneDX');
const build = text('engine/packaging/build_engine.py');
check(build.includes("engine/uv.lock is missing") && build.includes("platform.python_version()") && build.includes("PyInstaller"), 'release build fails closed on unlocked/runtime drift');
check(build.includes('mte-engine') && build.includes('compatibility.json') && build.includes('SHA256SUMS'), 'candidate build emits executable compatibility and digests');
const win = text('engine/packaging/windows/verify-package-signed.ps1');
check(win.includes('Get-AuthenticodeSignature') && win.includes("Status -ne 'Valid'") && win.includes('Compress-Archive'), 'Windows public packaging verifies Artifact Signing Authenticode before creating the final ZIP');
const winWorkflow = text('.github/workflows/release-engine-windows.yml');
check(winWorkflow.includes('Azure/artifact-signing-action@c7ab2a863ab5f9a846ddb8265964877ef296ee82') && winWorkflow.includes('azure/login@532459ea530d8321f2fb9bb10d1e0bcf23869a43') && winWorkflow.includes('timestamp.acs.microsoft.com'), 'Windows public workflow uses pinned Microsoft Artifact Signing v2 with OIDC and SHA-256 timestamping');
check(!winWorkflow.includes('MTE_SIGNTOOL') && !winWorkflow.includes('MTE_ARTIFACT_SIGNING_DLIB') && !winWorkflow.includes('MTE_ARTIFACT_SIGNING_METADATA'), 'Windows public workflow no longer assumes local signing paths on an ephemeral hosted runner');
const mac = text('engine/packaging/macos/sign-notarize.sh');
check(mac.includes('codesign --force --options runtime') && mac.includes('notarytool submit') && mac.includes('--key-id') && mac.includes('--issuer') && mac.includes('stapler staple') && mac.includes('stapler validate'), 'macOS script supports direct App Store Connect API-key notarization plus hardened runtime/stapling');
const macWorkflow = text('.github/workflows/release-engine-macos.yml');
check(macWorkflow.includes('security create-keychain') && macWorkflow.includes('MTE_MACOS_APPLICATION_P12_BASE64') && macWorkflow.includes('MTE_NOTARY_KEY_P8_BASE64') && !macWorkflow.includes('secrets.MTE_NOTARY_PROFILE'), 'macOS public workflow materializes signing identities and notarization key on the ephemeral runner');

const workflowDir = resolve(root, '.github/workflows');
const workflows = readdirSync(workflowDir).filter((name) => name.endsWith('.yml'));
check(workflows.length >= 6, 'CI and OS release workflows are separated');
const useRe = /^\s*-?\s*uses:\s*([^\s]+)\s*(?:#.*)?$/gm;
for (const name of workflows) {
  const value = text(`.github/workflows/${name}`);
  for (const match of value.matchAll(useRe)) {
    const reference = match[1];
    check(/^[^@\s]+@[0-9a-f]{40}$/.test(reference), `${name} pins ${reference} to a full commit SHA`);
  }
}
const allWorkflows = workflows.map((name) => text(`.github/workflows/${name}`)).join('\n');
check(!/uses:\s*[^\s]+@(v\d+|main|master)\b/.test(allWorkflows), 'no workflow action uses a mutable tag/branch');
check(allWorkflows.includes('actions/attest@') && allWorkflows.includes('id-token: write') && allWorkflows.includes('attestations: write'), 'release candidates add GitHub provenance attestations');
check(text('.github/workflows/release-engine-windows.yml').includes('release-windows'), 'Windows signing secrets are scoped to a release environment');
check(text('.github/workflows/release-engine-macos.yml').includes('release-macos'), 'macOS signing secrets are scoped to a release environment');

const forbiddenExtensions = new Set(['.pfx', '.p12', '.key', '.onnx', '.pdparams', '.pth', '.pt', '.safetensors']);
const forbidden = [];
function walk(dir) {
  for (const entry of readdirSync(dir)) {
    if (['node_modules', '.git', '.output', '.wxt', '.venv', '__pycache__', '.pytest_cache', '.offline-check'].includes(entry)) continue;
    const path = resolve(dir, entry); const st = statSync(path);
    if (st.isDirectory()) walk(path);
    else if (forbiddenExtensions.has(extname(path).toLowerCase())) forbidden.push(relative(root, path));
  }
}
walk(root);
check(forbidden.length === 0, `repository contains no private signing keys or embedded production model weights: ${forbidden.join(', ')}`);
console.log(`Phase 7 contracts: ${passed}/${passed} passed`);
