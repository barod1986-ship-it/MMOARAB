import { createHash } from 'node:crypto';
import { existsSync, readFileSync, realpathSync } from 'node:fs';
import { extname, isAbsolute, relative, resolve } from 'node:path';

const projectRoot = resolve('.');
const statePath = resolve(process.argv[2] ?? 'store/publication-state.json');
const allowMissing = process.argv.includes('--allow-missing');
const state = JSON.parse(readFileSync(statePath, 'utf8'));
const blockers = [];
const ok = [];

const checkImage = async (label, rel, width, height, allowedRoot) => {
  if (!rel) { blockers.push(`${label}: missing path`); return; }
  if (typeof rel !== 'string' || isAbsolute(rel)) { blockers.push(`${label}: path must be project-relative`); return; }
  const path = resolve(projectRoot, rel);
  const root = resolve(projectRoot, allowedRoot);
  const relToRoot = relative(root, path);
  if (relToRoot.startsWith('..') || isAbsolute(relToRoot)) { blockers.push(`${label}: path must stay under ${allowedRoot}`); return; }
  if (!existsSync(path)) { blockers.push(`${label}: file not found: ${rel}`); return; }
  if (realpathSync(path) !== path) { blockers.push(`${label}: symlinked asset paths are not accepted`); return; }
  const ext = extname(path).toLowerCase();
  if (!['.png', '.jpg', '.jpeg'].includes(ext)) { blockers.push(`${label}: unsupported format ${ext}`); return; }
  const bytes = readFileSync(path);
  const dims = imageDimensions(bytes, ext);
  if (!dims || dims.width !== width || dims.height !== height) {
    blockers.push(`${label}: expected ${width}x${height}, got ${dims ? `${dims.width}x${dims.height}` : 'unknown'}`);
    return;
  }
  ok.push({ label, path: rel, sha256: createHash('sha256').update(bytes).digest('hex'), width, height });
};

await checkImage('store icon', state.assets?.storeIcon128, 128, 128, 'store/assets');
await checkImage('small promo', state.assets?.smallPromo440x280, 440, 280, 'store/assets');

const promoVideo = state.assets?.promoVideoYoutube;
if (typeof promoVideo !== 'string' || promoVideo.length === 0) {
  blockers.push('promo video: real YouTube URL required');
} else {
  try {
    const url = new URL(promoVideo);
    const host = url.hostname.toLowerCase();
    if (url.protocol !== 'https:' || !['youtube.com', 'www.youtube.com', 'youtu.be'].includes(host)) blockers.push('promo video: HTTPS YouTube URL required');
    else ok.push({ label: 'promo video', url: promoVideo });
  } catch { blockers.push('promo video: invalid URL'); }
}
if (state.assets?.marquee1400x560) await checkImage('marquee promo', state.assets.marquee1400x560, 1400, 560, 'store/assets');

for (const [locale, files] of Object.entries(state.assets?.localizedScreenshots ?? {})) {
  if (!Array.isArray(files) || files.length === 0) {
    blockers.push(`screenshots ${locale}: no real screenshots recorded`);
    continue;
  }
  if (files.length > 5) blockers.push(`screenshots ${locale}: Chrome Web Store allows at most 5`);
  for (let i = 0; i < files.length; i++) await checkImage(`screenshot ${locale} #${i + 1}`, files[i], 1280, 800, 'store/screenshots');
}

if (blockers.length) {
  console.error(`Store assets not ready (${blockers.length} blocker(s)):`);
  for (const blocker of blockers) console.error(`- ${blocker}`);
  if (!allowMissing) process.exit(2);
} else {
  console.log(`Store assets verified: ${ok.length} file(s)`);
}

function imageDimensions(bytes, ext) {
  if (ext === '.png') {
    if (bytes.length < 24 || bytes.toString('ascii', 1, 4) !== 'PNG') return null;
    return { width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20) };
  }
  // Minimal JPEG SOF parser; enough for release-gate dimensions without adding a dependency.
  if (bytes[0] !== 0xff || bytes[1] !== 0xd8) return null;
  let offset = 2;
  while (offset + 9 < bytes.length) {
    if (bytes[offset] !== 0xff) { offset++; continue; }
    const marker = bytes[offset + 1];
    offset += 2;
    if (marker === 0xd8 || marker === 0xd9) continue;
    if (offset + 2 > bytes.length) break;
    const length = bytes.readUInt16BE(offset);
    if (length < 2 || offset + length > bytes.length) break;
    if ([0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf].includes(marker)) {
      return { height: bytes.readUInt16BE(offset + 3), width: bytes.readUInt16BE(offset + 5) };
    }
    offset += length;
  }
  return null;
}
