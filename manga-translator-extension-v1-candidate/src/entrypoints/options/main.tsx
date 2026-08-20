import React, { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { browser } from 'wxt/browser';
import { ENGINE_BASE_URL, ENGINE_HOST_PATTERN, type EngineCapabilities, type EngineConnectionSummary, type EngineModelCatalog } from '../../engine/types.js';
import { sendMessage } from '../../messaging/protocol.js';
import type { CacheStats } from '../../cache/result-cache.js';
import type { SafeDiagnostics } from '../../ui/diagnostics.js';
import { applyDocumentLocale, createTranslator, type MessageKey } from '../../ui/i18n.js';
import { DEFAULT_UI_SETTINGS, type UiSettings } from '../../ui/settings.js';
import { applyTheme } from '../../ui/theme.js';
import './style.css';

type ProbeState = 'idle' | 'probing' | 'reachable' | 'failed' | 'lna-denied';

function App() {
  const [settings, setSettings] = useState<UiSettings>(structuredClone(DEFAULT_UI_SETTINGS));
  const [draft, setDraft] = useState<UiSettings>(structuredClone(DEFAULT_UI_SETTINGS));
  const [engine, setEngine] = useState<EngineConnectionSummary>({ hostPermission: false, paired: false });
  const [capabilities, setCapabilities] = useState<EngineCapabilities | null>(null);
  const [modelCatalog, setModelCatalog] = useState<EngineModelCatalog | null>(null);
  const [cache, setCache] = useState<CacheStats>({ approxBytes: 0, approxEntries: 0 });
  const [probeState, setProbeState] = useState<ProbeState>('idle');
  const [token, setToken] = useState('');
  const [showToken, setShowToken] = useState(false);
  const [notice, setNotice] = useState('');
  const [diagnostics, setDiagnostics] = useState<SafeDiagnostics | null>(null);
  const t = useMemo(() => createTranslator(draft.uiLocale), [draft.uiLocale]);

  const refresh = useCallback(async () => {
    const [nextSettings, nextEngine, nextCache] = await Promise.all([
      sendMessage('ui:get-settings', {}),
      sendMessage('engine:get-state', { probeAuthenticated: true }),
      sendMessage('ui:get-cache-stats', {})
    ]);
    setSettings(nextSettings);
    setDraft(nextSettings);
    setEngine(nextEngine);
    setCache(nextCache);
    applyDocumentLocale(nextSettings.uiLocale);
    applyTheme(nextSettings.theme);
    if (nextEngine.hostPermission && nextEngine.paired && nextEngine.reachable) {
      const [caps, catalog] = await Promise.all([
        sendMessage('ui:get-capabilities', {}).catch(() => null),
        sendMessage('ui:get-model-catalog', {}).catch(() => null)
      ]);
      setCapabilities(caps);
      setModelCatalog(catalog);
    } else {
      setCapabilities(null);
      setModelCatalog(null);
    }
  }, []);

  useEffect(() => { void refresh().catch((error) => setNotice(errorMessage(error))); }, [refresh]);

  const save = async () => {
    setNotice('');
    try {
      const saved = await sendMessage('ui:set-settings', { settings: draft });
      setSettings(saved);
      setDraft(saved);
      applyDocumentLocale(saved.uiLocale);
      applyTheme(saved.theme);
      setNotice(t('saved'));
      setCache(await sendMessage('ui:get-cache-stats', {}));
    } catch (error) { setNotice(errorMessage(error)); }
  };

  const requestLoopback = async () => {
    setNotice('');
    try {
      const granted = await browser.permissions.request({ origins: [ENGINE_HOST_PATTERN] });
      setNotice(granted ? t('permissionGranted') : t('permissionDenied'));
      if (granted) await probeLocalEngine();
      else await refresh();
    } catch (error) { setNotice(errorMessage(error)); }
  };

  const probeLocalEngine = async () => {
    setProbeState('probing'); setNotice('');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 2500);
    try {
      const response = await fetch(`${ENGINE_BASE_URL}/healthz`, {
        method: 'GET',
        cache: 'no-store',
        credentials: 'omit',
        redirect: 'error',
        signal: controller.signal
      });
      if (response.status !== 204) throw new Error(`HTTP ${response.status}`);
      setProbeState('reachable');
      setNotice(t('probeReachable'));
    } catch {
      const lna = await localNetworkPermissionState();
      setProbeState(lna === 'denied' ? 'lna-denied' : 'failed');
      setNotice(lna === 'denied' ? t('lnaDenied') : t('probeFailed'));
    } finally {
      clearTimeout(timeout);
      const next = await sendMessage('engine:get-state', { probeAuthenticated: false }).catch(() => ({ hostPermission: false, paired: false }));
      setEngine(next);
    }
  };

  const pair = async () => {
    setNotice('');
    try {
      const paired = await sendMessage('engine:pair', { token });
      setToken('');
      setEngine(paired);
      const caps = await sendMessage('ui:get-capabilities', {});
      setCapabilities(caps);
      setModelCatalog(await sendMessage('ui:get-model-catalog', {}).catch(() => null));
      setNotice(t('pairingSuccess'));
    } catch (error) {
      setNotice(`${t('pairingFailed')} ${errorMessage(error)}`);
      setCapabilities(null);
    }
  };

  const disconnect = async () => {
    await sendMessage('engine:disconnect', {});
    setToken(''); setCapabilities(null); setModelCatalog(null); setProbeState('idle');
    setEngine(await sendMessage('engine:get-state', { probeAuthenticated: false }));
  };

  const refreshModelCatalog = useCallback(async () => {
    const catalog = await sendMessage('ui:get-model-catalog', {}).catch(() => null);
    setModelCatalog(catalog);
    return catalog;
  }, []);

  const installModel = async (artifactId: string) => {
    setNotice('');
    try {
      await sendMessage('ui:install-model', { artifactId });
      await refreshModelCatalog();
      setNotice(t('modelInstallStarted'));
    } catch (error) { setNotice(errorMessage(error)); }
  };

  const cancelModelInstall = async (ticket: string) => {
    setNotice('');
    try {
      await sendMessage('ui:cancel-model-install', { ticket });
      await refreshModelCatalog();
      setNotice(t('modelInstallCancelled'));
    } catch (error) { setNotice(errorMessage(error)); }
  };

  useEffect(() => {
    if (!modelCatalog?.artifacts.some((artifact) => artifact.state === 'queued' || artifact.state === 'running')) return;
    const timer = window.setTimeout(() => { void refreshModelCatalog(); }, 1000);
    return () => window.clearTimeout(timer);
  }, [modelCatalog, refreshModelCatalog]);

  const clearCache = async () => {
    const report = await sendMessage('ui:clear-cache', {});
    setCache({ approxBytes: report.remainingBytes, approxEntries: report.remainingEntries, lastGcAt: Date.now() });
    setNotice(t('cacheCleared'));
  };

  const copyDiagnostics = async () => {
    const tab = (await browser.tabs.query({ active: true, currentWindow: true }))[0];
    const value = await sendMessage('ui:get-diagnostics', { tabId: tab?.id ?? -1 });
    setDiagnostics(value);
    await navigator.clipboard.writeText(JSON.stringify(value, null, 2));
    setNotice(t('diagnosticsCopied'));
  };

  const selectedProfile = capabilities?.profiles.find((profile) => profile.profileId === draft.profileId);
  const connected = engine.hostPermission && engine.paired && engine.reachable;
  const cacheMiB = Math.round((cache.approxBytes / 1024 / 1024) * 10) / 10;
  const dirty = JSON.stringify(settings) !== JSON.stringify(draft);

  return <main className="settings-shell">
    <header className="page-header">
      <div><h1>{t('settings')}</h1><p>{t('aboutText')}</p></div>
      <button className="primary" type="button" disabled={!dirty} onClick={save}>{t('save')}</button>
    </header>

    {notice && <div className="notice" role="status" aria-live="polite">{notice}</div>}

    <div className="layout">
      <nav className="toc" aria-label={t('settings')}>
        {['general','translation','localEngine','provider','appearance','keyboardControls','storageCache','diagnostics','about'].map((key) =>
          <a key={key} href={`#${key}`}>{t(key as MessageKey)}</a>)}
      </nav>

      <div className="sections">
        <Section id="general" title={t('general')}>
          <div className="form-grid">
            <Field label={t('uiLanguage')}><select value={draft.uiLocale} onChange={(e) => { const uiLocale = e.currentTarget.value as UiSettings['uiLocale']; setDraft({ ...draft, uiLocale }); applyDocumentLocale(uiLocale); }}><option value="system">{t('browserDefault')}</option><option value="en">{t('english')}</option><option value="ar">{t('arabic')}</option></select></Field>
            <Field label={t('defaultSource')}><select value={draft.sourceLanguage} onChange={(e) => setDraft({ ...draft, sourceLanguage: e.currentTarget.value })}>{(capabilities?.supportedSourceLanguages ?? ['en','auto','ja','ko','zh-Hans','zh-Hant']).map((code) => <option value={code} key={code}>{languageName(code, t)}</option>)}</select></Field>
            <Field label={t('defaultTarget')}><select value="ar" disabled><option value="ar">{languageName('ar', t)}</option></select></Field>
            <Field label={t('defaultProfile')}><select value={draft.profileId} onChange={(e) => setDraft({ ...draft, profileId: e.currentTarget.value })}>{(capabilities?.profiles ?? [{ profileId: 'default-v1', state: 'needs-download' }]).map((p) => <option value={p.profileId} key={p.profileId}>{p.profileId} — {profileStateLabel(p.state, t)}</option>)}</select></Field>
          </div>
          <Check label={t('compactControls')} checked={draft.showCompactControls} onChange={(checked) => setDraft({ ...draft, showCompactControls: checked })} />
          <Check label={t('autoShowResult')} checked={draft.autoShowTranslatedResult} onChange={(checked) => setDraft({ ...draft, autoShowTranslatedResult: checked })} />
        </Section>

        <Section id="translation" title={t('translation')}>
          <dl className="key-values"><div><dt>{t('from')}</dt><dd>{languageName(draft.sourceLanguage, t)}</dd></div><div><dt>{t('to')}</dt><dd>{languageName('ar', t)}</dd></div><div><dt>SFX</dt><dd>{t('sfxPolicy')}</dd></div></dl>
          <p className="muted">{t('privacyLocal')}</p>
        </Section>

        <Section id="localEngine" title={t('localEngine')}>
          <ol className="steps">
            <li><strong>{t('engineHostPermission')}</strong><span>{engine.hostPermission ? t('permissionGranted') : t('enginePermissionMissing')}</span>{!engine.hostPermission && <button type="button" onClick={requestLoopback}>{t('allowLoopback')}</button>}</li>
            <li><strong>{t('probe')}</strong><span>{probeLabel(probeState, t)}</span><button type="button" disabled={!engine.hostPermission || probeState === 'probing'} onClick={probeLocalEngine}>{t('probe')}</button></li>
            <li><strong>{t('pairingToken')}</strong><span>{engine.paired ? t('pairingSuccess') : t('enginePairingRequired')}</span>{!engine.paired && <div className="token-row"><input autoComplete="off" spellCheck={false} type={showToken ? 'text' : 'password'} value={token} onChange={(e) => setToken(e.currentTarget.value)} aria-label={t('pairingToken')} /><button type="button" onClick={() => setShowToken((v) => !v)}>{showToken ? t('hide') : t('show')}</button><button type="button" className="primary" disabled={token.trim().length < 20} onClick={pair}>{t('pair')}</button></div>}</li>
            <li><strong>{t('capabilities')}</strong><span>{connected ? `${engine.engineVersion ?? '—'} · ${profileStateLabel(selectedProfile?.state ?? engine.profileState, t)}` : t('engineOffline')}</span>{engine.paired && <button type="button" onClick={disconnect}>{t('disconnect')}</button>}</li>
          </ol>
          <div className={`gate ${selectedProfile?.state === 'ready' ? 'ready' : 'blocked'}`}><strong>{t('productionGate')}</strong><p>{selectedProfile?.state === 'ready' ? t('engineReady') : t('productionGateBlocked')}</p></div>
          {capabilities && <dl className="key-values">
            <div><dt>{t('engineVersionLabel')}</dt><dd>{capabilities.engineVersion}</dd></div>
            <div><dt>{t('sourceLanguages')}</dt><dd>{capabilities.supportedSourceLanguages.map((code) => languageName(code, t)).join(', ')}</dd></div>
            <div><dt>{t('targetLanguages')}</dt><dd>{capabilities.supportedTargetLanguages.map((code) => languageName(code, t)).join(', ')}</dd></div>
            <div><dt>{t('hardware')}</dt><dd>{Object.entries(capabilities.hardware).filter(([, enabled]) => enabled).map(([name]) => name.toUpperCase()).join(', ') || '—'}</dd></div>
            <div><dt>{t('recommendedConcurrency')}</dt><dd>{capabilities.recommendedConcurrency}</dd></div>
          </dl>}
          {connected && modelCatalog && <div className="model-catalog">
            <div className="section-subhead"><div><strong>{t('modelCatalog')}</strong><p className="muted mono">{modelCatalog.catalogRevision}</p></div><button type="button" onClick={() => void refreshModelCatalog()}>{t('recheck')}</button></div>
            {modelCatalog.artifacts.length === 0 ? <p className="muted">{t('modelCatalogEmpty')}</p> : <div className="model-list">
              {modelCatalog.artifacts.map((artifact) => {
                const progress = artifact.bytes ? Math.min(100, Math.round((artifact.downloadedBytes / artifact.bytes) * 100)) : 0;
                const active = artifact.state === 'queued' || artifact.state === 'running';
                const ready = artifact.state === 'ready' || artifact.state === 'succeeded';
                return <article className="model-item" key={artifact.artifactId}>
                  <div><strong>{artifact.artifactId}</strong><p className="muted">{artifact.revision} · {formatBytes(artifact.bytes)} · {artifact.licenseSpdx}</p></div>
                  <div className="model-state"><span>{modelStateLabel(artifact.state, t)}</span>{active && <progress max={artifact.bytes} value={artifact.downloadedBytes} aria-label={`${artifact.artifactId} ${progress}%`} />}</div>
                  {artifact.error && <p className="error-text">{artifact.error.message}</p>}
                  <div className="button-row">
                    {!ready && !active && <button className="primary" type="button" onClick={() => void installModel(artifact.artifactId)}>{t('installModel')}</button>}
                    {active && artifact.ticket && <button type="button" onClick={() => void cancelModelInstall(artifact.ticket!)}>{t('cancel')}</button>}
                  </div>
                </article>;
              })}
            </div>}
          </div>}
        </Section>

        <Section id="provider" title={t('provider')}>
          <p>{selectedProfile ? privacyText(selectedProfile.privacy, t) : t('privacyRemoteText')}</p>
          <p className="muted">{t('privacyNoTelemetry')}</p>
          <p className="muted">{t('providerManaged')}</p>
        </Section>

        <Section id="appearance" title={t('appearance')}>
          <Field label={t('theme')}><select value={draft.theme} onChange={(e) => { const theme = e.currentTarget.value as UiSettings['theme']; setDraft({ ...draft, theme }); applyTheme(theme); }}><option value="system">{t('system')}</option><option value="light">{t('light')}</option><option value="dark">{t('dark')}</option></select></Field>
        </Section>

        <Section id="keyboardControls" title={t('keyboardControls')}><p>{t('keyboardHelp')}</p></Section>

        <Section id="storageCache" title={t('storageCache')}>
          <Check label={t('cacheTranslated')} checked={draft.cacheEnabled} onChange={(checked) => setDraft({ ...draft, cacheEnabled: checked })} />
          <Field label={t('cacheMaximum')}><select value={draft.cacheMaxMiB} onChange={(e) => setDraft({ ...draft, cacheMaxMiB: Number(e.currentTarget.value) as UiSettings['cacheMaxMiB'] })}><option value={128}>128 MiB</option><option value={256}>256 MiB</option><option value={512}>512 MiB</option></select></Field>
          <p>{t('cacheUsage')}: <strong>{cacheMiB} MiB</strong> · {t('itemCount', String(cache.approxEntries))}</p>
          <button type="button" onClick={clearCache}>{t('clearCache')}</button>
        </Section>

        <Section id="diagnostics" title={t('diagnostics')}>
          <p>{t('diagnosticsPrivacy')}</p>
          <button type="button" onClick={copyDiagnostics}>{t('copyDiagnostics')}</button>
          {diagnostics && <pre>{JSON.stringify(diagnostics, null, 2)}</pre>}
        </Section>

        <Section id="about" title={t('about')}><p>{t('aboutText')}</p><p>{t('privacyNoTelemetry')}</p><p className="mono">{t('extensionVersionLabel', browser.runtime.getManifest().version)}</p></Section>
      </div>
    </div>
  </main>;
}

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return <section id={id} className="section-card"><h2>{title}</h2>{children}</section>;
}

function Field({ label, children }: { label: string; children: ReactNode }) { return <label className="field"><span>{label}</span>{children}</label>; }
function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) { return <label className="check"><input type="checkbox" checked={checked} onChange={(e) => onChange(e.currentTarget.checked)} /><span>{label}</span></label>; }

function languageName(code: string, t: ReturnType<typeof createTranslator>): string {
  if (code === 'auto') return t('autoLanguage');
  try { return new Intl.DisplayNames([document.documentElement.lang || 'en'], { type: 'language' }).of(code) ?? code; } catch { return code; }
}

function profileStateLabel(state: string | undefined, t: ReturnType<typeof createTranslator>): string {
  if (state === 'ready') return t('profileStateReady');
  if (state === 'needs-download') return t('profileStateNeedsDownload');
  if (state === 'unavailable-hardware') return t('profileStateUnavailableHardware');
  if (state === 'misconfigured-provider') return t('profileStateMisconfiguredProvider');
  if (state === 'renderer-missing') return t('profileStateRendererMissing');
  if (state === 'runtime-unavailable') return t('profileStateRuntimeUnavailable');
  return '—';
}

function privacyText(privacy: { imageLeavesDevice: boolean; ocrTextLeavesDevice: boolean | null; visualContextLeavesDevice: boolean }, t: ReturnType<typeof createTranslator>): string {
  const parts: string[] = [];
  if (!privacy.imageLeavesDevice && privacy.ocrTextLeavesDevice === false && !privacy.visualContextLeavesDevice) return t('privacyLocal');
  if (privacy.imageLeavesDevice) parts.push(t('privacyImageMayLeave'));
  if (privacy.ocrTextLeavesDevice === true) parts.push(t('privacyTextMayLeave'));
  else if (privacy.ocrTextLeavesDevice === null) parts.push(t('privacyTextUnknown'));
  if (privacy.visualContextLeavesDevice) parts.push(t('privacyVisualMayLeave'));
  if (!privacy.imageLeavesDevice) parts.unshift(t('privacyLocal'));
  return parts.join(' ');
}

function modelStateLabel(state: string, t: ReturnType<typeof createTranslator>): string {
  if (state === 'ready' || state === 'succeeded') return t('modelStateReady');
  if (state === 'queued') return t('queued');
  if (state === 'running') return t('modelStateDownloading');
  if (state === 'failed') return t('failed');
  if (state === 'cancelled') return t('stageCancelled');
  return t('modelStateMissing');
}

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024 * 1024) return `${Math.round((bytes / 1024 / 1024 / 1024) * 10) / 10} GiB`;
  if (bytes >= 1024 * 1024) return `${Math.round((bytes / 1024 / 1024) * 10) / 10} MiB`;
  return `${Math.round(bytes / 1024)} KiB`;
}

function probeLabel(state: ProbeState, t: ReturnType<typeof createTranslator>): string {
  if (state === 'reachable') return t('probeReachable');
  if (state === 'lna-denied') return t('lnaDenied');
  if (state === 'failed') return t('probeFailed');
  if (state === 'probing') return t('refreshing');
  return '—';
}

async function localNetworkPermissionState(): Promise<PermissionState | 'unknown'> {
  const query = (navigator.permissions as unknown as { query(input: { name: string }): Promise<PermissionStatus> }).query.bind(navigator.permissions);
  for (const name of ['loopback-network', 'local-network-access']) {
    try { return (await query({ name })).state; } catch { /* Chrome version/alias may not expose this descriptor. */ }
  }
  return 'unknown';
}

function errorMessage(error: unknown): string { return error instanceof Error ? error.message : String(error); }

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
