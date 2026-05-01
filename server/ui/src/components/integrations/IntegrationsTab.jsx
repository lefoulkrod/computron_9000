import { useCallback, useEffect, useMemo, useState } from 'react';

import Callout from '../primitives/Callout.jsx';
import ConfirmButton from '../primitives/ConfirmButton.jsx';
import AddIntegrationModal from './AddIntegrationModal.jsx';
import styles from './IntegrationsTab.module.css';

const SLUG_META = {
    icloud: {
        label: 'iCloud',
        icon: 'bi-envelope-at',
        category: 'Email & Calendar',
    },
    gmail: {
        label: 'Gmail',
        icon: 'bi-envelope-at',
        category: 'Email & Calendar',
    },
};

// Per-state visuals + helper copy. The supervisor reports the state on
// every list/add response — we just translate it into the row chrome.
const STATE_VIEW = {
    running: {
        dotClass: 'dotRunning',
        badgeClass: 'badgeSuccess',
        label: 'connected',
        helper: null,
    },
    auth_failed: {
        dotClass: 'dotError',
        badgeClass: 'badgeDanger',
        label: 'auth failed',
        helper: 'Credentials were rejected. Delete and re-add to refresh.',
    },
    broken: {
        dotClass: 'dotError',
        badgeClass: 'badgeDanger',
        label: 'not running',
        helper: 'Couldn\'t reach this integration. Delete and re-add.',
    },
};

export default function IntegrationsTab() {
    const [integrations, setIntegrations] = useState([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState(null);
    const [modalOpen, setModalOpen] = useState(false);
    const [removeError, setRemoveError] = useState(null);
    // Master-detail: which row's edit form fills the right pane.
    const [selectedId, setSelectedId] = useState(null);
    const [saveError, setSaveError] = useState(null);
    const [saving, setSaving] = useState(false);

    const fetchIntegrations = useCallback(async () => {
        setLoading(true);
        setLoadError(null);
        try {
            const resp = await fetch('/api/integrations');
            if (!resp.ok) {
                const body = await resp.json().catch(() => ({}));
                setLoadError({
                    code: body?.error?.code || 'ERROR',
                    message: body?.error?.message || `HTTP ${resp.status}`,
                });
                setIntegrations([]);
                return;
            }
            const data = await resp.json();
            setIntegrations(data.integrations || []);
        } catch (err) {
            setLoadError({
                code: 'NETWORK',
                message: err?.message || 'Failed to load integrations',
            });
            setIntegrations([]);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchIntegrations();
    }, [fetchIntegrations]);

    // Auto-select on load: when the list arrives, pick the first row if no
    // valid selection exists. Also clear the selection when the selected
    // row gets removed.
    useEffect(() => {
        if (integrations.length === 0) {
            if (selectedId !== null) setSelectedId(null);
            return;
        }
        const stillExists = integrations.some(i => i.id === selectedId);
        if (!stillExists) setSelectedId(integrations[0].id);
    }, [integrations, selectedId]);

    const handleAdded = useCallback((newRecord) => {
        setModalOpen(false);
        fetchIntegrations();
        if (newRecord?.id) setSelectedId(newRecord.id);
    }, [fetchIntegrations]);

    const handleRemove = useCallback(async (id) => {
        setRemoveError(null);
        try {
            const resp = await fetch(`/api/integrations/${encodeURIComponent(id)}`, {
                method: 'DELETE',
            });
            if (!resp.ok) {
                const body = await resp.json().catch(() => ({}));
                setRemoveError({
                    id,
                    message: body?.error?.message || `HTTP ${resp.status}`,
                });
                return;
            }
            await fetchIntegrations();
        } catch (err) {
            setRemoveError({ id, message: err?.message || 'Request failed' });
        }
    }, [fetchIntegrations]);

    const handleSave = useCallback(async (id, updates) => {
        setSaving(true);
        setSaveError(null);
        try {
            const resp = await fetch(`/api/integrations/${encodeURIComponent(id)}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates),
            });
            if (!resp.ok) {
                const body = await resp.json().catch(() => ({}));
                setSaveError({
                    id,
                    message: body?.error?.message || `HTTP ${resp.status}`,
                });
                return false;
            }
            await fetchIntegrations();
            return true;
        } catch (err) {
            setSaveError({ id, message: err?.message || 'Request failed' });
            return false;
        } finally {
            setSaving(false);
        }
    }, [fetchIntegrations]);

    const grouped = useMemo(() => groupByCategory(integrations), [integrations]);
    const selected = useMemo(
        () => decorate(integrations.find(i => i.id === selectedId)),
        [integrations, selectedId],
    );

    const removeMessage = removeError?.id === selectedId ? removeError.message : null;
    const saveMessage = saveError?.id === selectedId ? saveError.message : null;

    return (
        <div className={styles.container}>
            {loading ? (
                <div className={styles.loading}>Loading integrations…</div>
            ) : loadError ? (
                loadError.code === 'UNAVAILABLE' ? (
                    <UnavailableState onRetry={fetchIntegrations} />
                ) : (
                    <div className={styles.loadError}>
                        <Callout
                            tone="danger"
                            title="Couldn't load integrations"
                            description={loadError.message}
                        />
                        <button className={styles.btnOutline} onClick={fetchIntegrations}>
                            <i className="bi bi-arrow-clockwise" /> Retry
                        </button>
                    </div>
                )
            ) : integrations.length === 0 ? (
                <EmptyState onAdd={() => setModalOpen(true)} />
            ) : (
                <div className={styles.split}>
                    <ListPane
                        grouped={grouped}
                        selectedId={selectedId}
                        onSelect={setSelectedId}
                        onAdd={() => setModalOpen(true)}
                    />
                    {selected && (
                        <DetailPane
                            key={selected.id}
                            record={selected}
                            saving={saving}
                            saveError={saveMessage}
                            removeError={removeMessage}
                            onSave={(updates) => handleSave(selected.id, updates)}
                            onRemove={() => handleRemove(selected.id)}
                        />
                    )}
                </div>
            )}

            {modalOpen && (
                <AddIntegrationModal
                    onClose={() => setModalOpen(false)}
                    onAdded={handleAdded}
                />
            )}
        </div>
    );
}

function groupByCategory(integrations) {
    const groups = new Map();
    for (const item of integrations) {
        const meta = SLUG_META[item.slug] ?? { category: 'Other', icon: 'bi-plug', label: item.slug };
        const category = meta.category;
        if (!groups.has(category)) groups.set(category, []);
        groups.get(category).push({ ...item, meta });
    }
    return [...groups.entries()];
}

function decorate(item) {
    if (!item) return null;
    const meta = SLUG_META[item.slug] ?? { category: 'Other', icon: 'bi-plug', label: item.slug };
    return { ...item, meta };
}

function UnavailableState({ onRetry }) {
    return (
        <div className={styles.emptyState}>
            <div className={`${styles.emptyIcon} ${styles.emptyIconMuted}`}>
                <i className="bi bi-wifi-off" />
            </div>
            <div className={styles.emptyHeading}>Integrations unavailable</div>
            <div className={styles.emptyDesc}>
                The integrations service is temporarily unavailable. Try again in a moment.
            </div>
            <button
                className={styles.btnOutline}
                onClick={onRetry}
                data-testid="integrations-retry"
            >
                <i className="bi bi-arrow-clockwise" /> Try again
            </button>
        </div>
    );
}

function EmptyState({ onAdd }) {
    return (
        <div className={styles.emptyState}>
            <div className={styles.emptyIcon}><i className="bi bi-plug" /></div>
            <div className={styles.emptyHeading}>Connect your first integration</div>
            <div className={styles.emptyDesc}>
                Give Computron access to your email and calendar. Credentials stay
                encrypted in your own vault — the agent never sees them directly.
            </div>
            <button
                className={styles.btnFilledLg}
                onClick={onAdd}
                data-testid="integrations-add-first"
            >
                <i className="bi bi-plus-lg" /> Add integration
            </button>
        </div>
    );
}

function ListPane({ grouped, selectedId, onSelect, onAdd }) {
    return (
        <div className={styles.listPane}>
            <div className={styles.listHeader}>
                <span className={styles.listTitle}>Connected</span>
                <button
                    className={styles.listAddBtn}
                    onClick={onAdd}
                    data-testid="integrations-add-another"
                >
                    <i className="bi bi-plus-lg" /> ADD
                </button>
            </div>
            <div className={styles.listBody}>
                {grouped.map(([category, rows]) => (
                    <section key={category} className={styles.group}>
                        <div className={styles.groupLabel}>{category}</div>
                        {rows.map(row => (
                            <ListRow
                                key={row.id}
                                row={row}
                                selected={row.id === selectedId}
                                onClick={() => onSelect(row.id)}
                            />
                        ))}
                    </section>
                ))}
            </div>
        </div>
    );
}

function ListRow({ row, selected, onClick }) {
    const view = STATE_VIEW[row.state] ?? STATE_VIEW.running;
    return (
        <button
            type="button"
            className={`${styles.listItem} ${selected ? styles.listItemActive : ''}`}
            onClick={onClick}
            data-testid={`integrations-row-${row.id}`}
        >
            <div className={styles.rowIcon}><i className={`bi ${row.meta.icon}`} /></div>
            <div className={styles.rowInfo}>
                <div className={styles.rowTitle}>
                    <span className={styles.rowLabelText}>{row.label}</span>
                    <span className={`${styles.badge} ${styles[view.badgeClass]}`}>
                        <span className={`${styles.statusDot} ${styles[view.dotClass]}`} />
                        {view.label}
                    </span>
                </div>
                <div className={styles.rowDesc}>{row.id}</div>
            </div>
        </button>
    );
}

function DetailPane({ record, saving, saveError, removeError, onSave, onRemove }) {
    const [labelDraft, setLabelDraft] = useState(record.label);
    const [writesDraft, setWritesDraft] = useState(record.write_allowed);

    const view = STATE_VIEW[record.state] ?? STATE_VIEW.running;
    const canEditWrites = record.state === 'running';

    const labelTrimmed = labelDraft.trim();
    const dirty = (
        labelTrimmed !== record.label || writesDraft !== record.write_allowed
    );
    const canSave = dirty && labelTrimmed.length > 0 && !saving;

    const handleSave = useCallback(async () => {
        const updates = {};
        if (labelTrimmed !== record.label) updates.label = labelTrimmed;
        if (writesDraft !== record.write_allowed) updates.write_allowed = writesDraft;
        if (Object.keys(updates).length === 0) return;
        await onSave(updates);
    }, [labelTrimmed, writesDraft, record, onSave]);

    const handleCancel = useCallback(() => {
        setLabelDraft(record.label);
        setWritesDraft(record.write_allowed);
    }, [record]);

    return (
        <div className={styles.detailPane}>
            {/* Action bar — top, mirrors ProfileBuilder. Disconnect on the
                left as the destructive action; Cancel + Save right-aligned. */}
            <div className={styles.actionsBar}>
                <ConfirmButton
                    className={styles.deleteBtn}
                    label="Delete"
                    confirmLabel="Confirm?"
                    busyLabel="Deleting…"
                    title="Delete this integration"
                    onConfirm={onRemove}
                    data-testid={`integrations-remove-${record.id}`}
                />
                <div className={styles.actionsRight}>
                    <button
                        type="button"
                        className={styles.secondaryBtn}
                        onClick={handleCancel}
                        disabled={!dirty || saving}
                        data-testid={`integrations-cancel-${record.id}`}
                    >
                        Revert
                    </button>
                    <button
                        type="button"
                        className={styles.primaryBtn}
                        onClick={handleSave}
                        disabled={!canSave}
                        data-testid={`integrations-save-${record.id}`}
                    >
                        Save
                    </button>
                </div>
            </div>

            <div className={styles.formBody}>
                {view.helper && (
                    <Callout tone="warning" description={view.helper} />
                )}

                <section className={styles.section}>
                    <div className={styles.sectionLabel}>Label</div>
                    <input
                        className={styles.nameInput}
                        type="text"
                        value={labelDraft}
                        onChange={(e) => setLabelDraft(e.target.value)}
                        placeholder="Label"
                        data-testid={`integrations-label-input-${record.id}`}
                    />
                </section>

                <section className={styles.section}>
                    <div className={styles.sectionLabel}>Permissions</div>
                    <label className={styles.checkRow}>
                        <input
                            type="checkbox"
                            checked={writesDraft}
                            onChange={(e) => setWritesDraft(e.target.checked)}
                            disabled={!canEditWrites}
                            data-testid={`integrations-toggle-write-${record.id}`}
                        />
                        <span className={styles.checkLabel}>
                            Allow writes
                        </span>
                        <span className={styles.checkHelp}>
                            When off, this integration is read-only — it can fetch
                            information but can't send, move, or change anything.
                        </span>
                    </label>
                </section>

                <section className={styles.section}>
                    <div className={styles.sectionLabel}>Status</div>
                    <KvRow label="State" value={view.label} />
                    <KvRow label="Provider" value={record.slug} />
                    <KvRow
                        label="Capabilities"
                        value={
                            (record.capabilities || []).length > 0
                                ? record.capabilities.join(' · ')
                                : '—'
                        }
                    />
                </section>

                {saveError && (
                    <Callout tone="danger" description={saveError} />
                )}
                {removeError && (
                    <Callout tone="danger" description={removeError} />
                )}
            </div>
        </div>
    );
}

function KvRow({ label, value }) {
    return (
        <div className={styles.kv}>
            <span className={styles.kvKey}>{label}</span>
            <span className={styles.kvVal}>{value}</span>
        </div>
    );
}
