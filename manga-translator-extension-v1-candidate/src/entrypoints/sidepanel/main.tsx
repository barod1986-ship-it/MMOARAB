import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { browser } from 'wxt/browser';
import { sendMessage } from '../../messaging/protocol.js';
import { applyDocumentLocale, createTranslator, type MessageKey } from '../../ui/i18n.js';
import { applyTheme } from '../../ui/theme.js';
import { presentationForError } from '../../ui/error-presenter.js';
import type { UiSnapshot } from '../../ui/types.js';
import type { UiSettings } from '../../ui/settings.js';
import './style.css';

type PendingPermission = { origin: string; candidateId: string; sourceRevision: number };

function App() {
  const [tabId, setTabId] = useState<number | null>(null);
  const [snapshot, setSnapshot] = useState<UiSnapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string>('');
  const [pendingPermission, setPendingPermission] = useState<PendingPermission | null>(null);
  const requestSerial = useRef(0);
  const t = useMemo(() => createTranslator(snapshot?.settings.uiLocale ?? 'system'), [snapshot?.settings.uiLocale]);

  const refresh = useCallback(async () => {
    const serial = ++requestSerial.current;
    const tab = (await browser.tabs.query({ active: true, currentWindow: true }))[0];
    if (tab?.id === undefined) {
      if (serial === requestSerial.current) { setTabId(null); setSnapshot(null); }
      return;
    }
    const received = await sendMessage('ui:get-snapshot', { tabId: tab.id });
    if (serial !== requestSerial.current) return;
    const unsupported = received.pageState === 'inactive' && typeof tab.url === 'string' && !/^https?:/i.test(tab.url);
    const next = unsupported ? { ...received, pageState: 'unsupported-tab' as const } : received;
    setTabId(tab.id);
    setSnapshot(next);
    applyDocumentLocale(next.settings.uiLocale);
    applyTheme(next.settings.theme);
  }, []);

  useEffect(() => {
    void refresh();
    const onActivated = () => { void refresh(); };
    const onUpdated = (updatedTabId: number, info: { status?: string }) => {
      if (updatedTabId === tabId && info.status === 'complete') void refresh();
    };
    browser.tabs.onActivated.addListener(onActivated);
    browser.tabs.onUpdated.addListener(onUpdated);
    return () => {
      browser.tabs.onActivated.removeListener(onActivated);
      browser.tabs.onUpdated.removeListener(onUpdated);
    };
  }, [refresh, tabId]);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      if (cancelled) return;
      await refresh().catch(() => undefined);
      if (cancelled) return;
      const active = (snapshot?.queue?.active.length ?? 0) > 0;
      timer = setTimeout(tick, active ? 1000 : 2500);
    };
    timer = setTimeout(tick, 1000);
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [refresh, snapshot?.queue?.active.length]);

  const saveSettings = async (patch: Partial<UiSettings>) => {
    if (!snapshot) return;
    const settings = await sendMessage('ui:set-settings', { settings: { ...snapshot.settings, ...patch } });
    setSnapshot({ ...snapshot, settings });
    applyDocumentLocale(settings.uiLocale);
    applyTheme(settings.theme);
  };

  const activeProfile = snapshot?.capabilities?.profiles.find((profile) => profile.profileId === snapshot.settings.profileId);
  const remoteTransferReady = !snapshot?.remoteTransferConsentRequired || snapshot.remoteTransferConsentAccepted;
  const engineReady = Boolean(snapshot?.engine.hostPermission && snapshot.engine.paired && snapshot.engine.reachable && activeProfile?.state === 'ready' && remoteTransferReady);
  const sessionReady = snapshot?.pageState === 'ready' && Boolean(snapshot.session?.documentId);
  const candidates = useMemo(() => {
    const list = Object.values(snapshot?.session?.candidates ?? {});
    return list.sort((a, b) => (a.orderHint ?? Number.MAX_SAFE_INTEGER) - (b.orderHint ?? Number.MAX_SAFE_INTEGER) || a.candidateId.localeCompare(b.candidateId));
  }, [snapshot?.session?.candidates]);
  const actionable = candidates.filter((candidate) => (candidate.visibility ?? 'far') !== 'far');

  const translatePage = async () => {
    if (!snapshot?.session || tabId === null) return;
    setBusy(true); setNotice('');
    try {
      const result = await sendMessage('ui:translate-page', { tabId, sessionId: snapshot.session.sessionId, allowScreenshot: true });
      setNotice(`${result.queued} ${t('queued')}${result.skippedFar ? ` · ${result.skippedFar} ${t('skipped')}` : ''}`);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : t('errorGenericBody'));
    } finally { setBusy(false); }
  };

  const translateCandidate = async (candidateId: string, sourceRevision: number, allowScreenshot: boolean) => {
    if (!snapshot?.session || tabId === null) return;
    setBusy(true); setNotice('');
    try {
      const outcome = await sendMessage('ui:translate-candidate', { tabId, sessionId: snapshot.session.sessionId, candidateId, sourceRevision, allowScreenshot });
      if (!outcome.ok && outcome.failure.reason === 'permission-needed') {
        setPendingPermission({ origin: outcome.failure.origin, candidateId, sourceRevision });
      } else if (!outcome.ok) {
        setNotice(outcome.failure.reason === 'failed' ? `${outcome.failure.code}: ${outcome.failure.message}` : outcome.failure.reason);
      } else {
        setNotice(outcome.result.applied ? t('done') : t('queued'));
      }
      await refresh();
    } catch (error) { setNotice(error instanceof Error ? error.message : t('errorGenericBody')); }
    finally { setBusy(false); }
  };

  const grantPendingOrigin = async () => {
    if (!pendingPermission) return;
    let pattern: string;
    try {
      const url = new URL(pendingPermission.origin);
      if (url.protocol !== 'https:') throw new Error('https only');
      pattern = `${url.origin}/*`;
    } catch { setNotice(t('permissionDenied')); return; }
    const granted = await browser.permissions.request({ origins: [pattern] });
    if (!granted) { setNotice(t('permissionDenied')); return; }
    const pending = pendingPermission;
    setPendingPermission(null);
    await translateCandidate(pending.candidateId, pending.sourceRevision, false);
  };

  const useScreenshot = async () => {
    if (!pendingPermission) return;
    const pending = pendingPermission;
    setPendingPermission(null);
    await translateCandidate(pending.candidateId, pending.sourceRevision, true);
  };

  const cancelJob = async (jobId: string) => {
    if (!snapshot?.session || tabId === null) return;
    await sendMessage('ui:cancel-job', { tabId, sessionId: snapshot.session.sessionId, jobId });
    await refresh();
  };

  const restoreAll = async () => {
    if (!snapshot?.session || tabId === null) return;
    await sendMessage('page:restore-all', { sessionId: snapshot.session.sessionId }, { tabId, frameId: 0 }).catch(() => undefined);
    setNotice(t('originals'));
  };

  const acceptPrivacyDisclosure = async () => {
    if (tabId === null) return;
    setBusy(true); setNotice('');
    try {
      await sendMessage('ui:accept-privacy-disclosure', { tabId });
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : t('errorGenericBody'));
    } finally { setBusy(false); }
  };

  const acceptRemoteTransferDisclosure = async () => {
    setBusy(true); setNotice('');
    try {
      await sendMessage('ui:accept-remote-transfer-disclosure', {});
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : t('errorGenericBody'));
    } finally { setBusy(false); }
  };

  const pageStatus = snapshot ? statusLabel(snapshot.pageState, t) : t('statusActivating');
  const blocking = snapshot?.errors.find((item) => item.scope === 'blocking');

  if (snapshot && !snapshot.privacyConsentAccepted) {
    return <main className="shell">
      <header className="topbar">
        <div><h1>{t('appName')}</h1><p className="muted">{t('privacyDisclosurePending')}</p></div>
        <button className="icon-button" type="button" onClick={() => browser.runtime.openOptionsPage()} aria-label={t('settings')}>⚙</button>
      </header>
      <section className="card attention-card privacy-disclosure" role="dialog" aria-labelledby="privacy-disclosure-title" aria-describedby="privacy-disclosure-body">
        <h2 id="privacy-disclosure-title">{t('privacyDisclosureTitle')}</h2>
        <p id="privacy-disclosure-body">{t('privacyDisclosureBody')}</p>
        <ul>
          <li>{t('privacyDisclosureData')}</li>
          <li>{t('privacyDisclosureLocalOnly')}</li>
          <li>{t('privacyDisclosureRetention')}</li>
        </ul>
        <p className="muted">{t('privacyDisclosureNoAds')}</p>
        <div className="actions">
          <button className="primary" type="button" disabled={busy || tabId === null} onClick={() => void acceptPrivacyDisclosure()}>{t('privacyConsentButton')}</button>
          <button className="secondary" type="button" onClick={() => browser.runtime.openOptionsPage()}>{t('privacyDetailsButton')}</button>
        </div>
      </section>
      {notice && <div className="toast" role="status" aria-live="polite">{notice}</div>}
    </main>;
  }

  if (snapshot?.remoteTransferConsentRequired && !snapshot.remoteTransferConsentAccepted && activeProfile?.state === 'ready') {
    const providers = snapshot.remoteTransferProviders.join(', ');
    return <main className="shell">
      <header className="topbar">
        <div><h1>{t('appName')}</h1><p className="muted">{t('remotePrivacyDisclosurePending')}</p></div>
        <button className="icon-button" type="button" onClick={() => browser.runtime.openOptionsPage()} aria-label={t('settings')}>⚙</button>
      </header>
      <section className="card attention-card privacy-disclosure" role="dialog" aria-labelledby="remote-privacy-title" aria-describedby="remote-privacy-body">
        <h2 id="remote-privacy-title">{t('remotePrivacyDisclosureTitle')}</h2>
        <p id="remote-privacy-body">{t('remotePrivacyDisclosureBody', providers)}</p>
        <ul>
          <li>{t('remotePrivacyDisclosureData')}</li>
          <li>{t('remotePrivacyDisclosureLocalImages')}</li>
          <li>{t('remotePrivacyDisclosureSfx')}</li>
          <li>{t('remotePrivacyDisclosureBinding')}</li>
        </ul>
        <div className="actions">
          <button className="primary" type="button" disabled={busy || !providers} onClick={() => void acceptRemoteTransferDisclosure()}>{t('remotePrivacyConsentButton')}</button>
          <button className="secondary" type="button" onClick={() => browser.runtime.openOptionsPage()}>{t('privacyDetailsButton')}</button>
        </div>
      </section>
      {notice && <div className="toast" role="status" aria-live="polite">{notice}</div>}
    </main>;
  }

  return <main className="shell">
    <header className="topbar">
      <div><h1>{t('appName')}</h1><p className="muted" aria-live="polite">{pageStatus}</p></div>
      <button className="icon-button" type="button" onClick={() => browser.runtime.openOptionsPage()} aria-label={t('settings')}>⚙</button>
    </header>

    {!snapshot?.session && <section className="card info-card"><h2>{t('statusInactive')}</h2><p>{t('notActivatedHelp')}</p></section>}

    {blocking && <AttentionCard code={blocking.code} count={blocking.count} t={t} onSetup={() => browser.runtime.openOptionsPage()} onRetry={refresh} />}

    {pendingPermission && <section className="card attention-card" role="alert">
      <h2>{t('permissionTitle')}</h2><p>{t('permissionBody')}</p><code>{pendingPermission.origin}</code>
      <div className="actions"><button onClick={grantPendingOrigin}>{t('grantExactOrigin')}</button><button className="secondary" onClick={useScreenshot}>{t('useScreenshot')}</button></div>
    </section>}

    <section className="card">
      <div className="section-heading"><h2>{t('page')}</h2><span className="pill">{candidates.length}</span></div>
      <div className="form-grid">
        <label>{t('from')}<select value={snapshot?.settings.sourceLanguage ?? 'en'} disabled={!snapshot} onChange={(e) => void saveSettings({ sourceLanguage: e.currentTarget.value })}>
          {(snapshot?.capabilities?.supportedSourceLanguages ?? ['en','auto','ja','ko','zh-Hans','zh-Hant']).map((code) => <option key={code} value={code}>{languageName(code, t)}</option>)}
        </select></label>
        <label>{t('to')}<select value="ar" disabled><option value="ar">{languageName('ar', t)}</option></select></label>
        <label className="span-2">{t('profile')}<select value={snapshot?.settings.profileId ?? 'default-v1'} disabled={!snapshot} onChange={(e) => void saveSettings({ profileId: e.currentTarget.value })}>
          {(snapshot?.capabilities?.profiles ?? [{ profileId: 'default-v1', profileFingerprint: '', state: 'needs-download', privacy: { imageLeavesDevice: false, ocrTextLeavesDevice: null, visualContextLeavesDevice: false }, externalProviders: [] }]).map((profile) => <option key={profile.profileId} value={profile.profileId}>{profile.profileId} — {profileStateLabel(profile.state, t)}</option>)}
        </select></label>
      </div>
      <p className="policy-note">{t('sfxPolicy')}</p>
      {activeProfile && <p className="privacy-note">{privacySummary(activeProfile.privacy, t)}</p>}
      <button className="primary wide" type="button" disabled={busy || !engineReady || !sessionReady || actionable.length === 0} onClick={translatePage}>{t('translatePage')}</button>
      {!engineReady && snapshot?.session && <p className="muted">{engineBlockText(snapshot, activeProfile?.state, t)}</p>}
    </section>

    <section className="card">
      <div className="section-heading"><h2>{t('currentWork')}</h2><span className="pill">{snapshot?.queue?.active.length ?? 0}</span></div>
      {(snapshot?.queue?.active.length ?? 0) === 0 ? <p className="muted">{t('noWork')}</p> : <div className="job-list">
        {snapshot!.queue!.active.slice(0, 6).map((job) => <div className="job" key={job.jobId}>
          <div><strong>{stageLabel(job.engineStage ?? job.stage, t)}</strong><span className="mono">{job.candidateId.slice(-8)}</span></div>
          {job.progress ? <progress max={job.progress.total} value={job.progress.completed} aria-label={stageLabel(job.engineStage ?? job.stage, t)} /> : <div className="indeterminate" aria-hidden="true"><span /></div>}
          <button className="secondary compact" type="button" onClick={() => void cancelJob(job.jobId)}>{t('cancel')}</button>
        </div>)}
      </div>}
      <div className="actions"><button className="secondary" type="button" disabled={!snapshot?.session} onClick={restoreAll}>{t('originals')}</button></div>
    </section>

    {snapshot?.errors.some((item) => item.scope !== 'blocking') && <section className="card">
      <div className="section-heading"><h2>{t('attention')}</h2><span className="pill">{snapshot.errors.reduce((sum, item) => sum + item.count, 0)}</span></div>
      <div className="error-list">{snapshot.errors.filter((item) => item.scope !== 'blocking').map((item) => {
        const p = presentationForError(item.code); return <div className="error-row" key={item.code}><div><strong>{t(p.titleKey as MessageKey)}</strong><p>{t(p.bodyKey as MessageKey)}</p></div><span className="pill">{item.count}</span></div>;
      })}</div>
    </section>}

    <section className="card">
      <div className="section-heading"><h2>{t('detectedImages')}</h2><span className="pill">{actionable.length}/{candidates.length}</span></div>
      <div className="candidate-list">{candidates.slice(0, 12).map((candidate) => <div className="candidate" key={candidate.candidateId}>
        <div><strong>{candidateKindLabel(candidate.kind, t)}</strong><span className="mono">{visibilityLabel(candidate.visibility ?? 'far', t)} · {candidateStateLabel(candidate.state, t)} · {t('revisionLabel')} {candidate.sourceRevision}</span></div>
        <button className="secondary compact" type="button" disabled={busy || !engineReady || (candidate.visibility ?? 'far') === 'far'} onClick={() => void translateCandidate(candidate.candidateId, candidate.sourceRevision, false)}>{t('translateVisible')}</button>
      </div>)}</div>
      {candidates.length > 12 && <p className="muted">+{candidates.length - 12}</p>}
      {candidates.some((candidate) => (candidate.visibility ?? 'far') === 'far') && <p className="muted">{t('farDeferred')}</p>}
    </section>

    <section className="card privacy-card"><h2>{t('engine')}</h2><p>{engineReady ? t('engineReady') : snapshot?.engine.hostPermission ? snapshot.engine.paired ? t('engineConnectedBlocked') : t('enginePairingRequired') : t('enginePermissionMissing')}</p><p className="muted">{t('privacyLocal')} {t('privacyNoTelemetry')}</p><button className="secondary" onClick={() => browser.runtime.openOptionsPage()}>{t('openSetup')}</button></section>

    {notice && <div className="toast" role="status" aria-live="polite">{notice}</div>}
  </main>;
}

function AttentionCard({ code, count, t, onSetup, onRetry }: { code: string; count: number; t: ReturnType<typeof createTranslator>; onSetup: () => void; onRetry: () => Promise<void> }) {
  const p = presentationForError(code);
  return <section className="card attention-card" role="alert"><div className="section-heading"><h2>{t(p.titleKey as MessageKey)}</h2>{count > 1 && <span className="pill">{count}</span>}</div><p>{t(p.bodyKey as MessageKey)}</p><div className="actions">{p.action === 'open-engine-setup' && <button onClick={onSetup}>{t('openSetup')}</button>}{(p.action === 'recheck-engine' || p.action === 'retry') && <button onClick={() => void onRetry()}>{t('recheck')}</button>}</div></section>;
}

function statusLabel(state: UiSnapshot['pageState'], t: ReturnType<typeof createTranslator>): string {
  if (state === 'ready') return t('statusReady');
  if (state === 'activating') return t('statusActivating');
  if (state === 'error') return t('statusError');
  if (state === 'unsupported-tab') return t('statusUnsupported');
  return t('statusInactive');
}

function stageLabel(stage: string, t: ReturnType<typeof createTranslator>): string {
  const map: Record<string, MessageKey> = { acquiring:'stageAcquiring', 'staging-source':'stageHashing', hashing:'stageHashing', 'waiting-work':'stageWaitingWork', 'joined-work':'stageWaitingWork', queued:'stageQueued', submitting:'stageProcessing', processing:'stageProcessing', decode:'stageProcessing', detect:'stageProcessing', order:'stageProcessing', ocr:'stageProcessing', translate:'stageProcessing', mask:'stageProcessing', inpaint:'stageProcessing', typeset:'stageProcessing', composite:'stageProcessing', encode:'stageProcessing', delivering:'stageDelivering', 'ready-result':'stageResultReady', applied:'stageApplied', failed:'stageFailed', cancelled:'stageCancelled', stale:'stageStale' };
  return t(map[stage] ?? 'working');
}

function privacySummary(privacy: { imageLeavesDevice: boolean; ocrTextLeavesDevice: boolean | null; visualContextLeavesDevice: boolean }, t: ReturnType<typeof createTranslator>): string {
  const parts: string[] = [];
  if (!privacy.imageLeavesDevice && privacy.ocrTextLeavesDevice === false && !privacy.visualContextLeavesDevice) return t('privacyLocal');
  if (privacy.imageLeavesDevice) parts.push(t('privacyImageMayLeave'));
  if (privacy.ocrTextLeavesDevice === true) parts.push(t('privacyTextMayLeave'));
  else if (privacy.ocrTextLeavesDevice === null) parts.push(t('privacyTextUnknown'));
  if (privacy.visualContextLeavesDevice) parts.push(t('privacyVisualMayLeave'));
  if (!privacy.imageLeavesDevice) parts.unshift(t('privacyLocal'));
  return parts.join(' ');
}

function engineBlockText(snapshot: UiSnapshot, profileState: string | undefined, t: (key: MessageKey, substitutions?: string | string[]) => string): string {
  if (!snapshot.engine.hostPermission) return t('enginePermissionMissing');
  if (!snapshot.engine.paired) return t('enginePairingRequired');
  if (snapshot.engine.reachable === false) return t('engineOffline');
  if (profileState !== 'ready') return t('profileGateBlocked');
  return t('engineConnectedBlocked');
}

function languageName(code: string, t: ReturnType<typeof createTranslator>): string {
  if (code === 'auto') return t('autoLanguage');
  try { return new Intl.DisplayNames([document.documentElement.lang || 'en'], { type: 'language' }).of(code) ?? code; } catch { return code; }
}

function profileStateLabel(state: string, t: ReturnType<typeof createTranslator>): string {
  if (state === 'ready') return t('profileStateReady');
  if (state === 'needs-download') return t('profileStateNeedsDownload');
  if (state === 'unavailable-hardware') return t('profileStateUnavailableHardware');
  if (state === 'misconfigured-provider') return t('profileStateMisconfiguredProvider');
  if (state === 'renderer-missing') return t('profileStateRendererMissing');
  if (state === 'runtime-unavailable') return t('profileStateRuntimeUnavailable');
  return state;
}

function candidateKindLabel(kind: string, t: ReturnType<typeof createTranslator>): string {
  if (kind === 'img') return t('candidateImage');
  if (kind === 'canvas') return t('candidateCanvas');
  return t('candidateViewportRegion');
}


function candidateStateLabel(state: string | undefined, t: ReturnType<typeof createTranslator>): string {
  if (state === 'detected') return t('candidateStateDetected');
  if (state === 'waiting-load') return t('candidateStateWaitingLoad');
  if (state === 'ready') return t('candidateStateReady');
  if (state === 'permission-needed') return t('candidateStatePermission');
  if (state === 'acquired') return t('candidateStateAcquired');
  if (state === 'translated') return t('candidateStateTranslated');
  if (state === 'stale') return t('candidateStateStale');
  return t('candidateStateReady');
}

function visibilityLabel(visibility: string, t: ReturnType<typeof createTranslator>): string {
  if (visibility === 'visible') return t('visibilityVisible');
  if (visibility === 'near') return t('visibilityNear');
  return t('visibilityFar');
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
