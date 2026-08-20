import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { basename, resolve } from 'node:path';

const state = JSON.parse(readFileSync(resolve('store/publication-state.json'), 'utf8'));
const privacy = JSON.parse(readFileSync(resolve('store/release/profile-privacy.json'), 'utf8'));
const candidatePath = process.argv[2] ? resolve(process.argv[2]) : resolve('release/store/candidate.json');
const blockers = [];
const requireTrue = (value, label) => { if (value !== true) blockers.push(label); };
const requireHttps = (value, label) => {
  if (typeof value !== 'string' || !/^https:\/\//i.test(value)) blockers.push(`${label}: public HTTPS URL required`);
};

requireTrue(state.publicDistributionChosen, 'public distribution decision not recorded');
for (const [key, value] of Object.entries(state.publisher ?? {})) requireTrue(value, `publisher.${key} is not verified`);
for (const key of ['privacyPolicy','homepage','support','reviewerFixture','engineDownload']) requireHttps(state.publicUrls?.[key], `publicUrls.${key}`);
for (const [key, value] of Object.entries(state.dashboard ?? {})) requireTrue(value, `dashboard.${key} incomplete`);
for (const key of ['phase5bProductionFreezeReady','phase7NativeSupportReady','chrome148StoreSmokePassed','currentStableStoreSmokePassed']) {
  requireTrue(state.releaseGates?.[key], `releaseGates.${key} not passed`);
}
const recordedTestedHash = state.releaseGates?.testedZipSha256 ?? null;
const recordedCandidateHash = state.releaseGates?.storeCandidateZipSha256 ?? null;
for (const [label, value] of [['testedZipSha256', recordedTestedHash], ['storeCandidateZipSha256', recordedCandidateHash]]) {
  if (value !== null && !/^[0-9a-f]{64}$/i.test(value)) blockers.push(`${label} is not a valid SHA-256 when recorded`);
}
if (recordedTestedHash && recordedCandidateHash && recordedTestedHash !== recordedCandidateHash) blockers.push('recorded Store candidate ZIP hash differs from recorded tested ZIP hash');

if (privacy.schemaVersion !== 2) blockers.push('production profile privacy descriptor schema must be v2');
const fingerprintTargets = ['linux-x86_64','macos-arm64','windows-x86_64'];
const fingerprints = privacy.profileFingerprintsByTarget;
if (!fingerprints || typeof fingerprints !== 'object' || Array.isArray(fingerprints) || Object.keys(fingerprints).sort().join(',') !== fingerprintTargets.sort().join(',')) {
  blockers.push('frozen production profile per-target fingerprints missing');
} else {
  for (const target of fingerprintTargets) if (!/^[0-9a-f]{64}$/i.test(fingerprints[target] ?? '')) blockers.push(`frozen production profile fingerprint missing for ${target}`);
}
if (!/^[0-9a-f]{64}$/i.test(privacy.materializedFromControlledManifestSha256 ?? '')) blockers.push('production profile/privacy is not bound to a controlled manifest');
if (!privacy.privacyDescriptor || typeof privacy.privacyDescriptor !== 'object') blockers.push('frozen production privacy descriptor missing');
else {
  const remote = privacy.privacyDescriptor.imageLeavesDevice === true || privacy.privacyDescriptor.ocrTextLeavesDevice === true || privacy.privacyDescriptor.visualContextLeavesDevice === true;
  if (remote) {
    if (!privacy.remoteTransferConsentImplemented) blockers.push('remote-transfer profile requires separate in-product consent implementation');
    if (!Array.isArray(privacy.externalProviderNames) || privacy.externalProviderNames.length === 0) blockers.push('remote-transfer profile must name external provider(s)');
  }
}

if (!existsSync(candidatePath)) blockers.push(`candidate metadata missing: ${candidatePath}`);
else {
  const candidate = JSON.parse(readFileSync(candidatePath, 'utf8'));
  if (candidate.schemaVersion !== 2) blockers.push('public Store candidate metadata must use controlled schema v2');
  if (candidate.byteIdenticalToTestedZip !== true) blockers.push('candidate metadata does not assert byte identity');
  if (candidate.byteIdenticalToControlledExtension !== true) blockers.push('candidate metadata does not prove exact controlled Extension bytes');
  if (!/^[0-9a-f]{64}$/i.test(candidate.controlledManifestSha256 ?? '')) blockers.push('candidate metadata is not bound to a controlled manifest');
  if (!/^[0-9a-f]{64}$/i.test(candidate.storeSubmissionHandoffSha256 ?? '')) blockers.push('candidate metadata is not bound to a pre-Store handoff');
  if (!/^[0-9a-f]{64}$/i.test(candidate.orchestrationSessionSha256 ?? '')) blockers.push('candidate metadata is not bound to evidence-promoted orchestration');
  if (!/^[0-9a-f]{40}$/i.test(candidate.assemblySourceHeadSha ?? '') || !/^[0-9a-f]{40}$/i.test(candidate.qualifiedSourceHeadSha ?? '')) blockers.push('candidate metadata source identities are missing');
  if (!/^[0-9a-f]{64}$/i.test(candidate.sha256 ?? '') || candidate.sha256 !== candidate.testedSha256) blockers.push('candidate metadata does not prove Store ZIP == tested ZIP SHA-256');
  if (recordedTestedHash && candidate.sha256 !== recordedTestedHash) blockers.push('candidate hash differs from optional recorded testedZipSha256');
  if (recordedCandidateHash && candidate.sha256 !== recordedCandidateHash) blockers.push('candidate hash differs from optional recorded storeCandidateZipSha256');
  const artifact = typeof candidate.artifact === 'string' ? candidate.artifact : '';
  if (!artifact || basename(artifact) !== artifact || !artifact.toLowerCase().endsWith('.zip')) {
    blockers.push('candidate artifact must be a simple ZIP filename under release/store');
  } else {
    const zipPath = resolve('release/store', artifact);
    if (!existsSync(zipPath)) blockers.push('candidate ZIP file missing');
    else {
      const digest = createHash('sha256').update(readFileSync(zipPath)).digest('hex');
      if (digest !== candidate.sha256) blockers.push('candidate ZIP bytes do not match candidate.json SHA-256');
    }
  }
}

const privacyPolicy = readFileSync(resolve('store/privacy/privacy-policy.md'), 'utf8');
if (privacyPolicy.includes('{{SUPPORT_CONTACT_REQUIRED}}')) blockers.push('privacy policy still contains support-contact placeholder');

if (blockers.length) {
  console.error(`Chrome Web Store release is BLOCKED (${blockers.length} blocker(s)):`);
  for (const blocker of blockers) console.error(`- ${blocker}`);
  process.exit(2);
}
console.log('Chrome Web Store release-ready gate passed.');
