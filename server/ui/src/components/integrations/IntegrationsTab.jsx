import { useCallback, useEffect, useState } from 'react';

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
        helper: 'Credentials were rejected. Disconnect and re-add to refresh.',
    },
    broken: {
        dotClass: 'dotError',
        badgeClass: 'badgeDanger',
        label: 'not running',
        helper: 'Couldn\'t reach this integration. Disconnect and re-add.',
    },
};

export default function IntegrationsTab() {
    const [integrations, setIntegrations] = useState([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState(null);
    const [modalOpen, setModalOpen] = useState(false);
    const [removeError, setRemoveError] = useState(null);

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

    const handleAdded = () => {
        setModalOpen(false);
        fetchIntegrations();
    };

    const handleRemove = useCallback(async (id) => {
        setRemoveError(null);
        try {
            const resp = await fetch(`/api/integrations/${encodeURIComponent(id)}`, {
                method: 'DELETE',
            });
            if (!resp.ok && resp.status !== 204) {
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

    const grouped = groupByCategory(integrations);

    return (
        <div className={styles.container}>
            {loading ? (
                <div className={styles.loading}>Loading integrations…</div>
            ) : loadError ? (
                loadError.code === 'UNAVAILABLE' ? (
                    <UnavailableState onRetry={fetchIntegrations} />
                ) : (
                    <div className={styles.error}>
                        <i className="bi bi-exclamation-triangle" /> {loadError.message}
                        <button className={styles.btnOutline} onClick={fetchIntegrations}>Retry</button>
                    </div>
                )
            ) : integrations.length === 0 ? (
                <EmptyState onAdd={() => setModalOpen(true)} />
            ) : (
                <PopulatedList
                    grouped={grouped}
                    onAdd={() => setModalOpen(true)}
                    onRemove={handleRemove}
                    removeError={removeError}
                />
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

function UnavailableState({ onRetry }) {
    return (
        <div className={styles.emptyState}>
            <div className={`${styles.emptyIcon} ${styles.emptyIconMuted}`}>
                <i className="bi bi-wifi-off" />
            </div>
            <div className={styles.emptyHeading}>Integrations unavailable</div>
            <div className={styles.emptyDesc}>
                The integrations service isn't running right now. Start it and try again.
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

function PopulatedList({ grouped, onAdd, onRemove, removeError }) {
    return (
        <div className={styles.list}>
            {grouped.map(([category, rows]) => (
                <section key={category} className={styles.group}>
                    <div className={styles.groupLabel}>{category}</div>
                    {rows.map(row => (
                        <Row
                            key={row.id}
                            row={row}
                            error={removeError?.id === row.id ? removeError.message : null}
                            onRemove={() => onRemove(row.id)}
                        />
                    ))}
                </section>
            ))}
            <div className={styles.listFooter}>
                <button
                    className={styles.btnFilled}
                    onClick={onAdd}
                    data-testid="integrations-add-another"
                >
                    <i className="bi bi-plus-lg" /> Add integration
                </button>
            </div>
        </div>
    );
}

function Row({ row, error, onRemove }) {
    const view = STATE_VIEW[row.state] ?? STATE_VIEW.running;
    return (
        <div className={styles.row}>
            <div className={styles.rowIcon}><i className={`bi ${row.meta.icon}`} /></div>
            <div className={styles.rowInfo}>
                <div className={styles.rowTitle}>
                    {row.label}
                    <span className={`${styles.badge} ${styles[view.badgeClass]}`}>
                        <span className={`${styles.statusDot} ${styles[view.dotClass]}`} />
                        {view.label}
                    </span>
                    <span className={styles.badge}>
                        {row.write_allowed ? 'Read and write' : 'Read only'}
                    </span>
                </div>
                <div className={styles.rowDesc}>{row.id}</div>
                {view.helper && (
                    <div className={styles.rowHelper}>
                        <i className="bi bi-exclamation-triangle" /> {view.helper}
                    </div>
                )}
                {error && (
                    <div className={styles.rowError}>
                        <i className="bi bi-exclamation-triangle" /> {error}
                    </div>
                )}
            </div>
            <div className={styles.rowControl}>
                <ConfirmButton
                    icon="bi-trash3"
                    confirmLabel="Confirm?"
                    busyLabel="Removing…"
                    title="Disconnect"
                    onConfirm={onRemove}
                    data-testid={`integrations-remove-${row.id}`}
                />
            </div>
        </div>
    );
}
