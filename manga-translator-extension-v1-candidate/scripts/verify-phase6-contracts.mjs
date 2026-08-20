import { access, readFile } from 'node:fs/promises';

const root = new URL('../', import.meta.url);
const text = async (path) => await readFile(new URL(path, root), 'utf8');
const json = async (path) => JSON.parse(await text(path));
const exists = async (path) => { try { await access(new URL(path, root)); return true; } catch { return false; } };

const files = {
  package: await json('package.json'),
  manifest: await text('wxt.config.ts'),
  side: await text('src/entrypoints/sidepanel/main.tsx'),
  sideCss: await text('src/entrypoints/sidepanel/style.css'),
  options: await text('src/entrypoints/options/main.tsx'),
  optionsCss: await text('src/entrypoints/options/style.css'),
  protocol: await text('src/messaging/protocol.ts'),
  handlers: await text('src/messaging/background-handlers.ts'),
  settings: await text('src/ui/settings.ts'),
  diagnostics: await text('src/ui/diagnostics.ts'),
  snapshot: await text('src/ui/snapshot.ts'),
  gateway: await text('src/engine/local-processing-gateway.ts'),
  engineTypes: await text('src/engine/types.ts'),
  coordinator: await text('src/pipeline/coordinator.ts'),
  pipelineTypes: await text('src/pipeline/types.ts'),
  presentation: await text('src/page/presentation/index.ts'),
  pageSession: await text('src/page/session.ts'),
  sessionStore: await text('src/core/session-store.ts'),
  ci: await text('.github/workflows/ci-extension.yml'),
  en: await json('src/ui/locales/en.json'),
  ar: await json('src/ui/locales/ar.json'),
  chromeEn: await json('public/_locales/en/messages.json'),
  chromeAr: await json('public/_locales/ar/messages.json')
};

const joinedUi = `${files.side}\n${files.options}`;
const enKeys = Object.keys(files.en).sort();
const arKeys = Object.keys(files.ar).sort();
const chromeEnKeys = Object.keys(files.chromeEn).sort();
const chromeArKeys = Object.keys(files.chromeAr).sort();
const structuralLocales = ['ja', 'ko', 'zh_CN', 'zh_TW'];
const structuralPresent = (await Promise.all(structuralLocales.map((lang) => exists(`public/_locales/${lang}/messages.json`)))).every(Boolean);

const checks = [
  ['package is Phase 6 and React stack is pinned', ['0.6.0-phase6', '0.7.0-phase7', '0.8.0-phase8', '0.9.0-phase9', '0.10.0-v1candidate'].includes(files.package.version) && files.package.dependencies.react === '19.2.8' && files.package.dependencies['react-dom'] === '19.2.8' && files.package.devDependencies['@wxt-dev/module-react'] === '1.2.2'],
  ['WXT React module is enabled', files.manifest.includes("modules: ['@wxt-dev/module-react']")],
  ['manifest keeps Chrome 148, side panel and no default popup', files.manifest.includes("minimum_chrome_version: '148'") && files.manifest.includes('side_panel:') && !files.manifest.includes('default_popup')],
  ['Options page is declared and opens in its own tab', files.manifest.includes('options_ui:') && files.manifest.includes("page: 'options.html'") && files.manifest.includes('open_in_tab: true')],
  ['toolbar keyboard command remains a trusted _execute_action path', files.manifest.includes('_execute_action') && files.manifest.includes("default: 'Alt+Shift+M'")],
  ['English and Arabic application catalogs are complete and symmetric', JSON.stringify(enKeys) === JSON.stringify(arKeys) && enKeys.length >= 100],
  ['Chrome English and Arabic catalogs are complete and symmetric', JSON.stringify(chromeEnKeys) === JSON.stringify(chromeArKeys) && JSON.stringify(enKeys) === JSON.stringify(chromeEnKeys)],
  ['Japanese, Korean and Chinese locale structure exists from Phase 6', structuralPresent],
  ['Side Panel and Options are React entrypoints', files.side.includes("from 'react'") && files.options.includes("from 'react'") && files.side.includes('createRoot(') && files.options.includes('createRoot(')],
  ['Side Panel uses one controller polling loop with active/idle cadence', files.side.includes('active ? 1000 : 2500') && (files.side.match(/setTimeout\(/g)?.length ?? 0) <= 2],
  ['real job stage/progress is surfaced; no fake percent is synthesized', files.side.includes('job.progress') && files.side.includes('job.engineStage ?? job.stage') && !joinedUi.includes('Math.random')],
  ['SFX policy is read-only preserve-original and has no user toggle', files.settings.includes("sfxAction: 'preserve-original'") && files.settings.includes("uncertainAction: 'preserve-original'") && !joinedUi.toLowerCase().includes('translate sfx')],
  ['UI settings cannot modify target away from Arabic', files.settings.includes("targetLanguage: 'ar'") && files.settings.includes("v.targetLanguage === 'ar'")],
  ['auto-show preference reaches delivery and can retain a ready result without forcing presentation', files.coordinator.includes('autoShow: uiSettings.autoShowTranslatedResult') && files.pipelineTypes.includes("{ status: 'stored' }") && files.coordinator.includes("draft.stage = 'ready-result'") && files.pageSession.includes('storeResult(')],
  ['compact in-page result control is extension-owned, keyboard accessible and preserves stored translation when showing original', files.coordinator.includes('showCompactControls: uiSettings.showCompactControls') && files.presentation.includes("dataset.mteOwned = 'result-toggle'") && files.presentation.includes("this.#button.type = 'button'") && files.presentation.includes('#hideVisual')],
  ['candidate presentation state survives PageSnapshot persistence and is shown in Side Panel', files.sessionStore.includes('state: candidate.state') && files.side.includes('candidateStateLabel(candidate.state, t)')],
  ['UI ProcessingSpec is built inside trusted background state', files.handlers.includes('processingSpecFromSettings(settings)') && !files.protocol.includes('processingSpec: ProcessingSpec')],
  ['UI-only messages reject non-extension-page senders', files.handlers.includes('requireTrustedUiSender(message.sender)') && files.handlers.includes('uiCommandSenderAllowed') && files.handlers.includes("throw new Error('Unauthorized extension UI sender.')")],
  ['image-origin permission is exact HTTPS and requested only from Side Panel user action', files.side.includes("url.protocol !== 'https:'") && files.side.includes('browser.permissions.request({ origins: [pattern] })')],
  ['loopback host permission is requested only from Options setup', files.options.includes('browser.permissions.request({ origins: [ENGINE_HOST_PATTERN] })') && !files.side.includes('ENGINE_HOST_PATTERN')],
  ['Engine setup probes /healthz directly from an extension page for LNA UX', files.options.includes("fetch(`${ENGINE_BASE_URL}/healthz`") && files.options.includes("'loopback-network'") && files.options.includes("'local-network-access'")],
  ['pairing token is password-masked by default and never enters diagnostics', files.options.includes("type={showToken ? 'text' : 'password'}") && files.diagnostics.includes('SafeDiagnostics') && !files.diagnostics.toLowerCase().includes('token')],
  ['capabilities privacy descriptor is parsed and validated, not guessed by provider name', files.gateway.includes('Engine profile privacy descriptor is malformed.') && files.gateway.includes('ocrTextLeavesDevice') && files.options.includes('selectedProfile.privacy')],
  ['default-v1 production gate is visible and cannot be treated as ready when engine reports blocked', files.options.includes("selectedProfile?.state === 'ready'") && files.options.includes("t('productionGateBlocked')") && files.side.includes("activeProfile?.state === 'ready'")],
  ['Options includes required Phase 6 sections', ['general','translation','localEngine','provider','appearance','keyboardControls','storageCache','diagnostics','about'].every((name) => files.options.includes(`id=\"${name}\"`) || files.options.includes(`id="${name}"`))],
  ['cache controls expose only enabled/max/approximate usage/clear, not browsing-history entries', files.options.includes("t('cacheTranslated')") && files.options.includes("t('cacheMaximum')") && files.options.includes("sendMessage('ui:clear-cache'") && !files.options.toLowerCase().includes('manga title')],
  ['diagnostics are explicitly privacy-reduced and only count external origins', files.diagnostics.includes('grantedExternalOrigins') && files.diagnostics.includes("origin.startsWith('https://')") && !files.diagnostics.includes('pageUrl') && !files.diagnostics.includes('sourceText') && !files.diagnostics.includes('translatedText')],
  ['accessibility includes focus-visible, reduced motion and live status regions', files.sideCss.includes(':focus-visible') && files.optionsCss.includes(':focus-visible') && files.sideCss.includes('prefers-reduced-motion') && joinedUi.includes('aria-live')],
  ['Phase 6 CI runs UI contract gate after build checks', files.ci.includes('name: ci-extension') && files.ci.includes('npm run check:phase6-contracts')],
  ['no external telemetry endpoint is introduced by Phase 6 UI', !/https:\/\//.test(joinedUi) && !/telemetry|analytics|sentry/i.test(joinedUi.replaceAll("privacyNoTelemetry", ''))]
];

let failed = false;
for (const [name, ok] of checks) {
  console.log(`${ok ? 'ok' : 'not ok'} - ${name}`);
  if (!ok) failed = true;
}
console.log(`# ${checks.length} Phase 6 contract checks`);
if (failed) process.exitCode = 1;
