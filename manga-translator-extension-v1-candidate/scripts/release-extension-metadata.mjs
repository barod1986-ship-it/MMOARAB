import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { basename, resolve } from 'node:path';

const artifact = process.argv[2] ? resolve(process.argv[2]) : null;
if (!artifact || !existsSync(artifact)) throw new Error('Usage: node scripts/release-extension-metadata.mjs <extension.zip>');
if (!existsSync(resolve('package-lock.json'))) throw new Error('release metadata refused: package-lock.json is missing');
const out = resolve('release/extension-metadata');
mkdirSync(out, { recursive: true });
const sbom = execFileSync('npm', ['sbom', '--package-lock-only', '--sbom-format', 'cyclonedx'], { cwd: process.cwd(), encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
const parsed = JSON.parse(sbom);
if (parsed.bomFormat !== 'CycloneDX' || !String(parsed.specVersion ?? '').startsWith('1.') || !Array.isArray(parsed.components)) {
  throw new Error('npm CycloneDX output failed schema sanity checks');
}
writeFileSync(resolve(out, 'extension.cyclonedx.json'), JSON.stringify(parsed, null, 2) + '\n');
const digest = createHash('sha256').update(readFileSync(artifact)).digest('hex');
writeFileSync(resolve(out, 'SHA256SUMS'), `${digest}  ${basename(artifact)}\n`);
console.log(out);
