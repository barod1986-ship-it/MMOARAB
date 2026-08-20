import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve('.');
let passed = 0;
const check = (condition, label) => { if (!condition) throw new Error(`Phase 8 contract failed: ${label}`); passed++; };
const text = (path) => readFileSync(resolve(root, path), 'utf8');
const json = (path) => JSON.parse(text(path));

const pkg = json('package.json');
check(['0.8.0-phase8','0.9.0-phase9', '0.10.0-v1candidate'].includes(pkg.version), 'extension package version is Phase 8 or later release-hardening phase');
check(pkg.scripts?.['check:phase8-contracts'] === 'node scripts/verify-phase8-contracts.mjs', 'Phase 8 verifier is scripted');
check(pkg.scripts?.['check:store-release-ready'] === 'node scripts/verify-store-release-ready.mjs', 'strict Store release-ready gate is scripted');
check(pkg.scripts?.['check:store-assets'] === 'node scripts/verify-store-assets.mjs store/publication-state.json', 'Store asset verifier is scripted');
check(pkg.scripts?.['check:store-tools'] === 'python tests/store-tools-smoke.py', 'Store tooling smoke is scripted');
const assetVerifier = text('scripts/verify-store-assets.mjs');
check(assetVerifier.includes("'store/assets'") && assetVerifier.includes("'store/screenshots'"), 'Store asset paths are constrained to reviewed asset roots');
check(assetVerifier.includes('realpathSync(path) !== path'), 'Store asset verifier rejects symlinked evidence');

const config = text('wxt.config.ts');
check(config.includes("version: '0.8.0'") || config.includes("version: '0.9.0'") || config.includes("version: '0.10.0'"), 'manifest version is Phase 8 or later release-hardening version');
check(config.includes("minimum_chrome_version: '148'"), 'Store baseline remains Chrome 148');
check(config.includes("permissions: ['activeTab', 'scripting', 'storage', 'sidePanel', 'alarms']"), 'required permissions remain narrow and explicit');
check(!/(^|\n)\s*host_permissions\s*:/.test(config), 'no required host permissions were added');
check(config.includes("optional_host_permissions: ['https://*/*', 'http://127.0.0.1/*']"), 'only reviewed optional hosts remain');
check(config.includes("message_serialization: 'structured_clone'"), 'Chrome 148 structured clone contract remains');

const locales = ['en','ar','ja','ko','zh_CN','zh_TW'];
for (const locale of locales) {
  const messages = json(`public/_locales/${locale}/messages.json`);
  for (const key of ['appName','appDescription','actionTitle','commandDescription']) {
    check(typeof messages[key]?.message === 'string' && messages[key].message.trim().length > 0, `${locale} browser.i18n contains ${key}`);
  }
  const listing = text(`store/listing/${locale}.md`);
  check(listing.includes(`\`${locale}\``), `${locale} Store listing declares its locale`);
  const summaryLabels = { en: 'Summary', ar: 'الملخص', ja: '要約', ko: '요약', zh_CN: '摘要', zh_TW: '摘要' };
  const summaryLine = listing.split(/\r?\n/u).find((line) => line.includes(`**${summaryLabels[locale]}`));
  check(Boolean(summaryLine), `${locale} listing has a summary field`);
  if (summaryLine) {
    const summary = summaryLine.replace(/^.*?\*\*[^*]+\*\*\s*/u, '').trim();
    check([...summary].length <= 132, `${locale} listing summary is <=132 characters`);
  }
}

const purpose = json('store/single-purpose.json');
check(purpose.schemaVersion === 1 && purpose.canonicalEnglish.includes('explicitly activates'), 'single purpose is narrow and explicit-activation based');
check(purpose.canonicalEnglish.toLowerCase().includes('preserving sound effects'), 'single purpose includes SFX preservation');
for (const excluded of ['general web scraping','browser-history analysis','advertising or affiliate injection','automatic browsing']) {
  check(purpose.boundaries.excluded.includes(excluded), `single-purpose boundary excludes ${excluded}`);
}

const privacyConsent = text('src/ui/privacy-consent.ts');
check(privacyConsent.includes("PRIVACY_DISCLOSURE_VERSION = '2026-08-19.v1'"), 'first-run privacy disclosure is versioned');
check(privacyConsent.includes("browser.storage.local"), 'privacy consent is durable local state');
const background = text('src/entrypoints/background.ts');
check(background.includes('if (!await privacyConsent.isAccepted()) return;'), 'toolbar activation does not inject before privacy consent');
check(background.includes('browser.sidePanel.open'), 'privacy surface opens from toolbar user gesture');
check(background.includes('deactivateSessionsUntilCurrentConsent'), 'disclosure-version invalidation deactivates old page sessions');
check(background.includes("pipeline.cancelJob(job.jobId, 'explicit-user')"), 'work admitted under obsolete consent is cancelled rather than resumed');
check(background.includes('if (!await privacyConsent.isAccepted()) return;') && background.includes("pipeline.pump('alarm')"), 'queue alarms cannot resume processing without current consent');
check(background.includes('await activation.reinjectAfterNavigation') && background.includes('if (!await privacyConsent.isAccepted()) return;'), 'navigation reinjection is consent-gated');
const activation = text('src/core/activation.ts');
check(activation.includes('activateFromUi'), 'trusted UI can activate after consent');
const handlers = text('src/messaging/background-handlers.ts');
check(handlers.includes("errorCode: 'PRIVACY_CONSENT_REQUIRED'") && handlers.includes("if (!await privacyConsent.isAccepted())"), 'background page/work handlers enforce current consent, not UI visibility alone');
for (const message of ['ui:get-privacy-consent','ui:accept-privacy-disclosure']) {
  const pos = handlers.indexOf(`onMessage('${message}'`);
  check(pos >= 0, `${message} handler exists`);
  check(handlers.slice(pos, pos + 500).includes('requireTrustedUiSender'), `${message} is restricted to trusted extension UI`);
}
const panel = text('src/entrypoints/sidepanel/main.tsx');
check(panel.includes('!snapshot.privacyConsentAccepted'), 'Side Panel blocks normal UI before consent');
check(panel.includes("sendMessage('ui:accept-privacy-disclosure'"), 'Side Panel requires explicit acceptance action');
check(panel.includes("t('privacyDisclosureLocalOnly')"), 'disclosure states local consent does not authorize remote transfer');

const dataInventory = text('store/privacy/data-inventory.md');
for (const token of ['Current-page origin','Comic image bytes','OCR text','Translated text','Pairing token','Local diagnostics']) check(dataInventory.includes(token), `data inventory covers ${token}`);
check(dataInventory.toLowerCase().includes('local-only processing'), 'local-only data handling is explicitly disclosed');
const privacyPolicy = text('store/privacy/privacy-policy.md');
for (const token of ['First-run disclosure and consent','Local processing','Translation providers','Storage and retention','Limited Use','Changes']) check(privacyPolicy.includes(token), `privacy policy includes ${token}`);
check(privacyPolicy.includes('does not scan browsing history in the background'), 'privacy policy distinguishes current-page access from browsing-history collection');
check(privacyPolicy.includes('does not sell user data'), 'privacy policy prohibits sale');
const limitedUse = text('store/privacy/limited-use.md');
check(limitedUse.includes('personalized advertising') && limitedUse.includes('data brokers'), 'Limited Use disclosure blocks prohibited monetization');
const dashboard = text('store/privacy/dashboard-declarations.md');
check(dashboard.includes('**No.**') && dashboard.toLowerCase().includes('remote code'), 'Dashboard remote-code declaration is No');
check(dashboard.toLowerCase().includes('website content'), 'Dashboard guide declares website content');

const permissions = text('store/permissions.md');
for (const permission of ['`activeTab`','`scripting`','`storage`','`sidePanel`','`alarms`','Optional `https://*/*`','Optional `http://127.0.0.1/*`']) check(permissions.includes(permission), `permission justification covers ${permission}`);
for (const forbidden of ['`tabs`','`history`','`webRequest`','`cookies`','`downloads`']) check(permissions.includes(forbidden), `permissions document explicitly calls out absent ${forbidden}`);

const reviewer = text('store/review-notes.md');
check(reviewer.includes('no page session/images are detected before consent'), 'reviewer path tests the first-run privacy gate');
check(reviewer.includes('sound effects remain unchanged'), 'reviewer path tests SFX preservation');
check(reviewer.includes('There are no developer-owned website credentials or hidden review accounts'), 'review path has no hidden account backdoor');

const screenshotPlan = text('store/screenshots/README.md');
check(screenshotPlan.includes('1280×800'), 'screenshot contract uses preferred Store dimensions');
for (const shot of ['01-first-run-privacy.png','02-detected-page.png','03-translated-result.png','04-local-engine-setup.png','05-cache-diagnostics.png']) check(screenshotPlan.includes(shot), `screenshot plan includes ${shot}`);
check(screenshotPlan.includes('Do not submit mockups'), 'Store screenshots must be real product captures');
const assets = text('store/assets/README.md');
check(assets.includes('128×128') && assets.includes('440×280') && assets.includes('1400×560'), 'Store asset dimensions are documented');
check(assets.includes('YouTube'), 'required Store promotional video is documented');

const state = json('store/publication-state.json');
check(state.publicDistributionChosen === false, 'public distribution is not falsely claimed before decision/account work');
check(state.publisher.twoStepVerificationVerified === false, '2-Step Verification is not falsely claimed');
check(state.publicUrls.privacyPolicy === null, 'unhosted privacy policy URL is an explicit blocker');
check(state.assets.promoVideoYoutube === null, 'unrecorded required Store promo video is an explicit blocker');
check(state.releaseGates.testedZipSha256 === null && state.releaseGates.storeCandidateZipSha256 === null, 'untested Store artifact hashes are not invented');
const profilePrivacy = json('store/release/profile-privacy.json');
check(profilePrivacy.schemaVersion === 2 && Object.values(profilePrivacy.profileFingerprintsByTarget ?? {}).every((value) => value === null) && profilePrivacy.privacyDescriptor === null, 'unfrozen per-target production privacy profile is not invented');
check(profilePrivacy.remoteTransferConsentImplemented === false, 'remote data transfer is blocked until separate consent exists');

const candidateScript = text('scripts/prepare_store_candidate.py');
for (const token of ['byteIdenticalToTestedZip','shutil.copyfile','manifest.json','minimum_chrome_version','host_permissions','structured_clone']) check(candidateScript.includes(token), `Store candidate promotion enforces ${token}`);
check(candidateScript.includes('FORBIDDEN_PREFIXES') && candidateScript.includes('engine/'), 'Store ZIP cannot accidentally bundle native Engine');
check(candidateScript.includes('PurePosixPath') && candidateScript.includes('{".", ".."}'), 'Store ZIP path traversal is rejected canonically');
check(candidateScript.includes('duplicate ZIP path') && candidateScript.includes('symlink entries are forbidden'), 'Store ZIP rejects duplicate and symlink entries');
const readyGate = text('scripts/verify-store-release-ready.mjs');
check(Object.prototype.hasOwnProperty.call(state.publisher, 'twoStepVerificationVerified') && readyGate.includes('Object.entries(state.publisher'), 'release-ready gate checks publisher verification including 2-Step Verification');
for (const token of ['privacyPolicy','phase5bProductionFreezeReady','phase7NativeSupportReady','chrome148StoreSmokePassed','candidate.testedSha256','candidate.sha256']) check(readyGate.includes(token), `release-ready gate checks ${token}`);
check(readyGate.includes('remote-transfer profile requires separate in-product consent'), 'release gate blocks undeclared remote profile transfer');
check(readyGate.includes('basename(artifact) !== artifact'), 'release gate constrains candidate artifact to release/store filename');
check(readyGate.includes('byteIdenticalToControlledExtension') && readyGate.includes('storeSubmissionHandoffSha256') && readyGate.includes('orchestrationSessionSha256'), 'Store release gate requires candidate binding to controlled bytes and pre-Store orchestration handoff');

const workflows = readdirSync(resolve(root, '.github/workflows')).filter((name) => name.endsWith('.yml'));
check(workflows.includes('prepare-store-candidate.yml'), 'Store candidate workflow exists');
const workflow = text('.github/workflows/prepare-store-candidate.yml');
check(!workflow.includes('publishers.items.publish') && !workflow.includes('wxt submit'), 'first Store submission workflow does not auto-publish');
check(workflow.includes('prepare_store_candidate.py') && workflow.includes('--controlled-manifest') && workflow.includes('--store-submission-handoff'), 'workflow promotes the exact controlled Extension ZIP without re-zipping');
check(workflow.includes('v1_evidence_orchestrator.py store-handoff') && workflow.includes('controlled_release_run_id'), 'Store candidate workflow requires the pre-Store public V1 gate and exact controlled archive provenance');
check(workflow.includes('npm run check:store-tools') && !workflow.includes('npm run zip'), 'Store candidate workflow tests promotion tooling and never rebuilds the Store ZIP');
check(workflow.includes('actions/attest@'), 'Store candidate is attested');

console.log(`Phase 8 contracts: ${passed}/${passed} passed`);
