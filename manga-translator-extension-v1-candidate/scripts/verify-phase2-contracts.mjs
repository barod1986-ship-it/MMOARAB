import assert from 'node:assert/strict';
import { readFile, access } from 'node:fs/promises';

const mockUrl = new URL('../src/pipeline/mock-gateway.ts', import.meta.url);
let gateway = '';
try { await access(mockUrl); gateway = await readFile(mockUrl, 'utf8'); } catch { gateway = await readFile(new URL('../src/engine/local-processing-gateway.ts', import.meta.url), 'utf8'); }

const [packageText, protocol, constants, schema, coordinator, detector] = await Promise.all([
  readFile(new URL('../package.json', import.meta.url), 'utf8'),
  readFile(new URL('../src/messaging/protocol.ts', import.meta.url), 'utf8'),
  readFile(new URL('../src/shared/constants.ts', import.meta.url), 'utf8'),
  readFile(new URL('../src/binary/schema.ts', import.meta.url), 'utf8'),
  readFile(new URL('../src/pipeline/coordinator.ts', import.meta.url), 'utf8'),
  readFile(new URL('../src/page/detector.ts', import.meta.url), 'utf8')
]);

const pkg = JSON.parse(packageText);
assert.equal(pkg.dependencies?.idb, '8.0.3');
assert.equal(pkg.devDependencies?.['fake-indexeddb'], '6.2.5');

assert.match(constants, /RUNTIME_DB_NAME\s*=\s*'manga-translation-runtime'/);
assert.match(constants, /RUNTIME_DB_VERSION\s*=\s*1/);
assert.match(constants, /MAX_SOURCE_BYTES\s*=\s*32\s*\*\s*1024\s*\*\s*1024/);
assert.match(constants, /MAX_RESULT_BYTES\s*=\s*32\s*\*\s*1024\s*\*\s*1024/);

for (const storeName of ['binaries', 'binaryLeases', 'cacheEntries', 'meta']) {
  assert.match(schema, new RegExp(`\\b${storeName}: \\{`), `missing IndexedDB store contract: ${storeName}`);
}
for (const indexName of ['by-binary-id', 'by-owner', 'by-owner-role', 'by-runtime-session']) {
  assert.ok(schema.includes(`'${indexName}'`), `missing binary lease index: ${indexName}`);
}

const intakeLine = protocol.split('\n').find((line) => line.includes("'pipeline:intake'")) ?? '';
assert.ok(intakeLine.includes('sessionId') && intakeLine.includes('candidateId') && intakeLine.includes('sourceRevision') && intakeLine.includes('acquired'));
for (const forbidden of ['binaryId', 'processingSpec', 'engineProfileFingerprint']) {
  assert.equal(intakeLine.includes(forbidden), false, `pipeline:intake must not expose ${forbidden}`);
}

assert.match(coordinator, /stageOwned\([\s\S]*role:\s*'source'/);
assert.match(coordinator, /stageOwned\([\s\S]*role:\s*'result'/);
assert.match(coordinator, /role:\s*'delivery'/);
assert.match(coordinator, /isJobFreshForDelivery/);
assert.match(coordinator, /finally\s*\{[\s\S]*#acquisitions\.release/);
assert.match(detector, /candidate\.sourceRevision\s*\+=\s*1/);
if (gateway.includes('MockProcessingGateway')) assert.equal(/https?:\/\//.test(gateway), false, 'Phase 2 mock gateway must not contain a network endpoint');
else assert.ok(gateway.includes("ENGINE_BASE_URL") || gateway.includes("/v1/jobs"), 'later phase must replace the Phase 2 mock with the audited Local Engine gateway');

console.log('Phase 2 contract checks passed.');
