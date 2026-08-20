import { readFile } from 'node:fs/promises';

const files = {
  constants: await readFile(new URL('../src/shared/constants.ts', import.meta.url), 'utf8'),
  coordinator: await readFile(new URL('../src/pipeline/coordinator.ts', import.meta.url), 'utf8'),
  cache: await readFile(new URL('../src/cache/result-cache.ts', import.meta.url), 'utf8'),
  cacheKey: await readFile(new URL('../src/cache/cache-key.ts', import.meta.url), 'utf8'),
  retry: await readFile(new URL('../src/queue/retry-wake.ts', import.meta.url), 'utf8'),
  workStore: await readFile(new URL('../src/queue/work-store.ts', import.meta.url), 'utf8'),
  ids: await readFile(new URL('../src/shared/ids.ts', import.meta.url), 'utf8'),
  background: await readFile(new URL('../src/entrypoints/background.ts', import.meta.url), 'utf8'),
  manifest: await readFile(new URL('../wxt.config.ts', import.meta.url), 'utf8')
};

const checks = [
  ['alarms permission is required', files.manifest.includes("'alarms'")],
  ['shared queue-wake alarm is fixed', files.constants.includes("QUEUE_WAKE_ALARM = 'queue-wake'")],
  ['Chrome 148 baseline does not use persistAcrossSessions', !Object.values(files).join('\n').includes('persistAcrossSessions:')],
  ['cache is bounded to 256 MiB by default', files.constants.includes('256 * 1024 * 1024')],
  ['cache TTL is 30 days', files.constants.includes('30 * 24 * 60 * 60 * 1000')],
  ['memory soft budget is 64 MiB', files.constants.includes('64 * 1024 * 1024')],
  ['prepared-ahead limit is 3', files.constants.includes('MAX_PREPARED_AHEAD_PER_SESSION = 3')],
  ['work dedupe is persisted by signature', files.workStore.includes('createOrGetBySignature') && files.workStore.includes('jobSignature')],
  ['cache key uses content/spec/profile namespace', files.cacheKey.includes('mte-result-cache-v1')],
  ['cache promotion is validated and lease-backed', files.cache.includes("ownerType: 'cache'") && files.cache.includes("role: 'cache'")],
  ['quota failure does not imply engine rerun', files.cache.includes("return 'skipped-quota'")],
  ['queue separates admission from work processing', files.coordinator.includes('#admitWaitingJobs') && files.coordinator.includes('#processOneWork')],
  ['engine lane is capped at one', files.coordinator.includes('#engineLane = new AsyncLane(1)')],
  ['hash lane is capped at one', files.coordinator.includes('#hashLane = new AsyncLane(1)')],
  ['acquisition lane is capped at two', files.coordinator.includes('#acquisitionLane = new AsyncLane(2)')],
  ['work id is deterministic from the final signature', files.ids.includes('workIdFromSignature') && files.ids.includes('work_v1_')],
  ['work source lease is acquired before publishing a new WorkRecord', files.coordinator.indexOf("ownerType: 'work'") < files.coordinator.indexOf('createOrGetBySignature(proposed)')],
  ['consumer fan-out overflow is excluded from hydration', files.coordinator.includes('allowedJobs.push(...bucket.slice(0, MAX_WORK_CONSUMERS))') && files.coordinator.includes('for (const job of allowedJobs)')],
  ['background retry path has no long timers', !/setInterval|setTimeout/.test(files.background + files.retry)],
  ['manifest version remains at or beyond Phase 3', /version:\s*'0\.(?:[3-9]|[1-9][0-9]+)\./.test(files.manifest)]
];

let failed = false;
for (const [name, ok] of checks) {
  console.log(`${ok ? 'ok' : 'not ok'} - ${name}`);
  if (!ok) failed = true;
}
if (failed) process.exitCode = 1;
