import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve('.');
const text = (p) => readFileSync(resolve(root, p), 'utf8');
const json = (p) => JSON.parse(text(p));
const fail = (message) => { throw new Error(`Toolchain policy failed: ${message}`); };
const requireContains = (path, token) => {
  if (!text(path).includes(token)) fail(`${path} must contain ${token}`);
};

const policy = json('release-control/toolchain.json');
if (policy.schemaVersion !== 1) fail('unsupported toolchain schema');
const { node, npm } = policy.canonicalExtensionBuild;
const { python, uv } = policy.canonicalEngineBuild;
if (!/^\d+\.\d+\.\d+$/.test(node) || !/^\d+\.\d+\.\d+$/.test(npm)) fail('canonical Node/npm pins must be exact versions');
if (!/^\d+\.\d+\.\d+$/.test(python) || !/^\d+\.\d+\.\d+$/.test(uv)) fail('canonical Python/uv pins must be exact versions');
if (text('.nvmrc').trim() !== node) fail('.nvmrc must match canonical Node');
if (text('.python-version').trim() !== python) fail('.python-version must match canonical Python');

const pkg = json('package.json');
if (pkg.packageManager !== `npm@${npm}`) fail('packageManager must pin canonical npm');
if (!String(pkg.engines?.node || '').includes('>=22')) fail('package engines must retain Node 22+ compatibility');
if (!pkg.scripts?.['check:toolchain']) fail('check:toolchain script missing');

const pyproject = text('engine/pyproject.toml');
for (const token of [
  'fastapi==0.141.1',
  'pydantic==2.13.4',
  'uvicorn==0.52.3',
  'pillow==12.3.0',
  'pyinstaller==6.22.2',
]) requireContains('engine/pyproject.toml', token);
if (!pyproject.includes('requires-python = ">=3.11"')) fail('Engine Python compatibility floor drifted');

for (const workflow of ['.github/workflows/release-extension.yml', '.github/workflows/controlled-release.yml']) {
  requireContains(workflow, `node-version: '${node}'`);
  requireContains(workflow, `npm@${npm}`);
}
for (const workflow of [
  '.github/workflows/release-engine-linux.yml',
  '.github/workflows/release-engine-macos.yml',
  '.github/workflows/release-engine-windows.yml',
  '.github/workflows/controlled-release.yml',
]) {
  requireContains(workflow, `python-version: '${python}'`);
  requireContains(workflow, `uv==${uv}`);
}

const bootstrap = '.github/workflows/bootstrap-dependency-locks.yml';
for (const token of [
  `node-version: '${node}'`,
  `npm@${npm}`,
  `python-version: '${python}'`,
  `uv==${uv}`,
  'npm install --package-lock-only',
  'npm ci',
  'uv lock',
  'uv lock --check',
  'update_source_sha256s.py',
  'package-lock.json',
  'engine/uv.lock',
]) requireContains(bootstrap, token);

console.log(`Toolchain policy: Node ${node} / npm ${npm}; Python ${python} / uv ${uv}`);
