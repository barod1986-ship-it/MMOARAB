import { rm } from 'node:fs/promises';

await rm(new URL('../.offline-check/', import.meta.url), { recursive: true, force: true });
