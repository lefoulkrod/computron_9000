import { useCallback, useEffect, useMemo, useState } from 'react';

import Button from '../primitives/Button.jsx';
import Callout from '../primitives/Callout.jsx';
import ConfirmButton from '../primitives/ConfirmButton.jsx';
import StatusDot from '../StatusDot.jsx';
import { invalidateModelCache } from '../ModelPicker.jsx';
import AddProviderModal from './AddProviderModal.jsx';
import styles from './ProvidersTab.module.css';

// Per-name display data. Same labels the backend uses; icons chosen from
// Bootstrap Icons that read at-a-glance for each provider kind.
const PROVIDER_META = {
    ollama: { label: 'Ollama', icon: 'bi-cpu' },
    openai_compat: { label: 'OpenAI-compatible', icon: 'bi-hdd-network' },
    anthropic: { label: 'Anthropic', icon: 'bi-cloud' },
    openai: { label: 'OpenAI', icon: 'bi-cloud' },
    openrouter: { label: 'OpenRouter', icon: 'bi-router' },
};

// Backend status → StatusDot status + user-facing label. The supervisor
// reports brokered states (running / auth_failed / broken); direct
// providers are always "configured" at rest and "connected" after a probe.
const STATUS_VIEW = {
    connected: { dot: 'ready', label: 'connected' },
    configured: { dot: 'ready', label: 'configured' },
    running: { dot: 'ready', label: 'connected' },
    auth_failed: { dot: 'error', label: 'auth failed' },
    broken: { dot: 'error', label: 'not running' },
    unreachable: { dot: 'warn', label: "couldn't reach" },
};

function _meta(name) {
    return PROVIDER_META[name] ?? { label: name, icon: 'bi-plug' };
}
function _statusView(status) {
    return STATUS_VIEW[status] ?? { dot: 'warn', label: status };
}

export default function ProvidersTab() {
    const [providers, setProviders] = useState([]);
    // Effective status per provider — overlays the list response with
    // whatever the latest Test Connection saw (so a probe failure flips
    // the row without re-fetching /api/providers).
    const [statusOverrides, setStatusOverrides] = useState({});
    const [modelCounts, setModelCounts] = useState({});
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState(null);
    const [selectedName, setSelectedName] = useState(null);
    const [modalOpen, setModalOpen] = useState(false);

    const fetchProviders = useCallback(async () => {
        setLoading(true);
        setLoadError(null);
        try {
            const resp = await fetch('/api/providers');
            if (!resp.ok) {
                const body = await resp.json().catch(() => ({}));
                setLoadError(body?.error || `HTTP ${resp.status}`);
                setProviders([]);
                return;
            }
            const data = await resp.json();
            setProviders(data.providers || []);
        } catch (err) {
            setLoadError(err?.message || 'Failed to load providers');
            setProviders([]);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchProviders();
    }, [fetchProviders]);

    // Auto-select on load: first row if no valid selection.
    useEffect(() => {
        if (providers.length === 0) {
            if (selectedName !== null) setSelectedName(null);
            return;
        }
        const stillExists = providers.some(p => p.name === selectedName);
        if (!stillExists) setSelectedName(providers[0].name);
    }, [providers, selectedName]);

    // Probe each provider in parallel to populate model counts. Errors
    // are silent here — they surface via Test Connection on the detail pane.
    useEffect(() => {
        let cancelled = false;
        providers.forEach((p) => {
            fetch(`/api/models?provider=${encodeURIComponent(p.name)}`)
                .then(r => r.ok ? r.json() : Promise.reject(r))
                .then((data) => {
                    if (cancelled) return;
                    setModelCounts(prev => ({ ...prev, [p.name]: (data.models || []).length }));
                })
                .catch(() => {
                    if (cancelled) return;
                    setModelCounts(prev => ({ ...prev, [p.name]: null }));
                    setStatusOverrides(prev => ({ ...prev, [p.name]: 'unreachable' }));
                });
        });
        return () => { cancelled = true; };
    }, [providers]);

    const handleAdded = useCallback((created) => {
        setModalOpen(false);
        fetchProviders();
        if (created?.name) setSelectedName(created.name);
    }, [fetchProviders]);

    const handleRemove = useCallback(async (name) => {
        try {
            const resp = await fetch(`/api/providers/${encodeURIComponent(name)}`, {
                method: 'DELETE',
            });
            if (!resp.ok) {
                const body = await resp.json().catch(() => ({}));
                throw new Error(body.error || `HTTP ${resp.status}`);
            }
            invalidateModelCache(name);
            await fetchProviders();
        } catch (err) {
            // Surface as a load error since the row is gone or stuck.
            setLoadError(err?.message || 'Failed to remove provider');
        }
    }, [fetchProviders]);

    const selected = useMemo(
        () => providers.find(p => p.name === selectedName) || null,
        [providers, selectedName],
    );

    return (
        <div className={styles.container} data-testid="providers-tab">
            {loading ? (
                <div className={styles.loading}>Loading providers…</div>
            ) : loadError ? (
                <div className={styles.loadError}>
                    <Callout tone="danger" title="Couldn't load providers" description={loadError} />
                    <Button onClick={fetchProviders}>
                        <i className="bi bi-arrow-clockwise" /> Retry
                    </Button>
                </div>
            ) : providers.length === 0 ? (
                <EmptyState onAdd={() => setModalOpen(true)} />
            ) : (
                <div className={styles.split}>
                    <ListPane
                        providers={providers}
                        statusOverrides={statusOverrides}
                        modelCounts={modelCounts}
                        selectedName={selectedName}
                        onSelect={setSelectedName}
                        onAdd={() => setModalOpen(true)}
                    />
                    {selected && (
                        <DetailPane
                            key={selected.name}
                            provider={selected}
                            status={statusOverrides[selected.name] || selected.status}
                            modelCount={modelCounts[selected.name]}
                            onSaved={(probeResult) => {
                                // Reflect the freshly-probed state.
                                setStatusOverrides(prev => ({ ...prev, [selected.name]: 'connected' }));
                                if (probeResult?.models) {
                                    setModelCounts(prev => ({ ...prev, [selected.name]: probeResult.models.length }));
                                }
                                invalidateModelCache(selected.name);
                                fetchProviders();
                            }}
                            onTested={(ok, count) => {
                                setStatusOverrides(prev => ({
                                    ...prev,
                                    [selected.name]: ok ? 'connected' : 'unreachable',
                                }));
                                if (ok && count != null) {
                                    setModelCounts(prev => ({ ...prev, [selected.name]: count }));
                                    invalidateModelCache(selected.name);
                                }
                            }}
                            onRemove={() => handleRemove(selected.name)}
                        />
                    )}
                </div>
            )}

            {modalOpen && (
                <AddProviderModal
                    existingNames={providers.map(p => p.name)}
                    onClose={() => setModalOpen(false)}
                    onAdded={handleAdded}
                />
            )}
        </div>
    );
}


/* ── List pane ─────────────────────────────────────────────────────── */

function ListPane({ providers, statusOverrides, modelCounts, selectedName, onSelect, onAdd }) {
    return (
        <div className={styles.listPane}>
            <div className={styles.listHeader}>
                <div className={styles.listTitle}>Providers · {providers.length}</div>
                <button
                    type="button"
                    className={styles.listAddBtn}
                    onClick={onAdd}
                    data-testid="providers-add-btn"
                >
                    <i className="bi bi-plus-lg" /> Add
                </button>
            </div>
            {providers.map((p) => {
                const meta = _meta(p.name);
                const effectiveStatus = statusOverrides[p.name] || p.status;
                const view = _statusView(effectiveStatus);
                const count = modelCounts[p.name];
                const selected = p.name === selectedName;
                return (
                    <button
                        key={p.name}
                        type="button"
                        className={`${styles.listRow} ${selected ? styles.listRowSelected : ''}`}
                        onClick={() => onSelect(p.name)}
                        data-testid={`provider-row-${p.name}`}
                    >
                        <div className={styles.listIcon}>
                            <i className={`bi ${meta.icon}`} />
                        </div>
                        <div className={styles.listMain}>
                            <div className={styles.listName}>{meta.label}</div>
                            <div className={styles.listMeta}>
                                <StatusDot status={view.dot} /> {view.label}
                            </div>
                        </div>
                        <div className={styles.listCount}>
                            {count == null ? '—' : `${count} m`}
                        </div>
                    </button>
                );
            })}
        </div>
    );
}


/* ── Detail pane ───────────────────────────────────────────────────── */

function DetailPane({ provider, status, modelCount, onSaved, onTested, onRemove }) {
    const meta = _meta(provider.name);
    const view = _statusView(status);
    const isDirect = provider.kind === 'direct';

    const [field, setField] = useState(provider.base_url || '');
    // When the selected provider changes, reset the input.
    useEffect(() => { setField(provider.base_url || ''); }, [provider.name, provider.base_url]);

    const [saving, setSaving] = useState(false);
    const [saveError, setSaveError] = useState(null);
    const [testing, setTesting] = useState(false);
    const [testResult, setTestResult] = useState(null);

    const handleSave = useCallback(async () => {
        if (!field) return;
        setSaving(true);
        setSaveError(null);
        try {
            const body = isDirect ? { base_url: field } : { api_key: field };
            const resp = await fetch(`/api/providers/${encodeURIComponent(provider.name)}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) {
                setSaveError(data.message || data.error || `HTTP ${resp.status}`);
                return;
            }
            onSaved?.(data);
            if (!isDirect) setField(''); // clear the key field on success
        } catch (err) {
            setSaveError(err?.message || 'Request failed');
        } finally {
            setSaving(false);
        }
    }, [field, isDirect, provider.name, onSaved]);

    const handleTest = useCallback(async () => {
        setTesting(true);
        setTestResult(null);
        try {
            const resp = await fetch(`/api/models?provider=${encodeURIComponent(provider.name)}`);
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) {
                setTestResult({ ok: false, message: data.message || `HTTP ${resp.status}` });
                onTested?.(false, null);
                return;
            }
            const count = (data.models || []).length;
            setTestResult({ ok: true, count });
            onTested?.(true, count);
        } catch (err) {
            setTestResult({ ok: false, message: err?.message || 'Request failed' });
            onTested?.(false, null);
        } finally {
            setTesting(false);
        }
    }, [provider.name, onTested]);

    return (
        <div className={styles.detailPane} data-testid="provider-detail">
            <div className={styles.detailHeader}>
                <div className={styles.detailIcon}>
                    <i className={`bi ${meta.icon}`} />
                </div>
                <div>
                    <div className={styles.detailName}>{meta.label}</div>
                    <div className={styles.detailStatusLine}>
                        <span className={`${styles.badge} ${view.dot === 'ready' ? styles.badgeSuccess : view.dot === 'error' ? styles.badgeDanger : styles.badgeWarn}`}>
                            {view.label}
                        </span>
                        {modelCount != null && <span>· {modelCount} models</span>}
                    </div>
                </div>
            </div>

            <div className={styles.detailSection}>
                <div className={styles.detailSectionLabel}>
                    {isDirect ? 'Base URL' : 'API Key'}
                </div>
                <div className={styles.inputRow}>
                    <input
                        type={isDirect ? 'text' : 'password'}
                        className={`${styles.input} ${styles.inputMono}`}
                        value={field}
                        onChange={(e) => setField(e.target.value)}
                        placeholder={isDirect ? 'http://host:port' : 'Paste a new key to replace the current one'}
                        autoComplete={isDirect ? 'off' : 'new-password'}
                    />
                    <Button variant="filled" onClick={handleSave} disabled={saving || !field}>
                        {saving ? 'Saving…' : 'Save'}
                    </Button>
                </div>
                {!isDirect && (
                    <div className={styles.formHint}>
                        Stored encrypted in the vault. Saving restarts the broker.
                    </div>
                )}
                {saveError && (
                    <div className={`${styles.resultChip} ${styles.resultChipErr}`}>
                        <i className="bi bi-x-circle-fill" /> {saveError}
                    </div>
                )}
            </div>

            <div className={styles.detailSection}>
                <div className={styles.detailSectionLabel}>Connection</div>
                <div className={styles.detailActions}>
                    <Button onClick={handleTest} disabled={testing} data-testid="provider-test-btn">
                        <i className="bi bi-broadcast" /> {testing ? 'Testing…' : 'Test connection'}
                    </Button>
                </div>
                {testResult && testResult.ok && (
                    <div className={`${styles.resultChip} ${styles.resultChipOk}`}>
                        <i className="bi bi-check-circle-fill" /> Connected · {testResult.count} models
                    </div>
                )}
                {testResult && !testResult.ok && (
                    <div className={`${styles.resultChip} ${styles.resultChipErr}`}>
                        <i className="bi bi-x-circle-fill" /> {testResult.message}
                    </div>
                )}
            </div>

            <div className={styles.detailSectionLast}>
                <ConfirmButton
                    label="Remove"
                    confirmLabel="Confirm remove?"
                    icon="bi-trash"
                    onConfirm={onRemove}
                    className={styles.removeBtn}
                    data-testid="provider-remove-btn"
                />
            </div>
        </div>
    );
}


/* ── Empty state ───────────────────────────────────────────────────── */

function EmptyState({ onAdd }) {
    return (
        <div className={styles.emptyState}>
            <div className={styles.emptyIcon}><i className="bi bi-plug" /></div>
            <div className={styles.emptyHeading}>No providers configured</div>
            <div className={styles.emptyDesc}>
                Agents need at least one LLM provider to run. Add Ollama for local models,
                or a cloud API like Anthropic, OpenAI, or OpenRouter.
            </div>
            <Button variant="filled" onClick={onAdd} data-testid="providers-empty-add-btn">
                <i className="bi bi-plus-lg" /> Add Provider
            </Button>
        </div>
    );
}
