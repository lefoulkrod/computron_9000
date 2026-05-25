import { useState, useCallback } from 'react';
import TrashIcon from './icons/TrashIcon.jsx';
import EyeIcon from './icons/EyeIcon.jsx';
import useListPanel from '../hooks/useListPanel.js';
import styles from './MemoryTab.module.css';

/**
 * Memory tab inside Settings. Compact one-row-per-entry table:
 * key, value preview, hide-value toggle, delete. Hide just masks the
 * value in the UI — the value itself stays in the backend.
 */
export default function MemoryTab({ refreshSignal }) {
    const [hiddenKeys, setHiddenKeys] = useState(new Set());

    const onFetched = useCallback((data) => {
        if (Array.isArray(data.hidden)) setHiddenKeys(new Set(data.hidden));
    }, []);

    const {
        items: entries, loading,
        deleting, handleDelete,
    } = useListPanel('/api/memory', {
        refreshSignal,
        getId: ([key]) => key,
        transform: (data) => Object.entries(data.entries),
        onFetched,
    });

    const onDelete = (key) => {
        handleDelete(key, `/api/memory/${encodeURIComponent(key)}`, ([k]) => k !== key);
        setHiddenKeys((prev) => { const next = new Set(prev); next.delete(key); return next; });
    };

    const toggleHidden = async (key) => {
        const nowHidden = !hiddenKeys.has(key);
        setHiddenKeys((prev) => {
            const next = new Set(prev);
            if (nowHidden) next.add(key); else next.delete(key);
            return next;
        });
        try {
            await fetch(`/api/memory/${encodeURIComponent(key)}/hidden`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hidden: nowHidden }),
            });
        } catch (_) {
            // Revert local state if the request fails so the UI stays
            // truthful about what the backend will return next.
            setHiddenKeys((prev) => {
                const next = new Set(prev);
                if (nowHidden) next.delete(key); else next.add(key);
                return next;
            });
        }
    };

    return (
        <div className={styles.tab} data-testid="memory-tab">
            <div className={styles.header}>
                <span className={styles.title}>Memory</span>
                <span className={styles.count} data-testid="memory-count">
                    {loading ? '' : `${entries.length} ${entries.length === 1 ? 'memory' : 'memories'}`}
                </span>
            </div>
            {loading && <p className={styles.empty}>Loading…</p>}
            {!loading && entries.length === 0 && (
                <p className={styles.empty}>No memories yet.</p>
            )}
            {!loading && entries.length > 0 && (
                <table className={styles.table}>
                    <thead>
                        <tr>
                            <th className={styles.keyCol}>Key</th>
                            <th className={styles.valueCol}>Value</th>
                            <th className={styles.actionCol}>Hide</th>
                            <th className={styles.actionCol}></th>
                        </tr>
                    </thead>
                    <tbody>
                        {entries.map(([key, value]) => {
                            const isHidden = hiddenKeys.has(key);
                            return (
                                <tr key={key} data-testid="memory-row" data-key={key}>
                                    <td className={styles.key}>{key}</td>
                                    <td
                                        className={styles.value}
                                        title={isHidden ? undefined : value}
                                        data-testid="memory-value"
                                    >
                                        {isHidden ? '••••••••' : value}
                                    </td>
                                    <td className={styles.actionCol}>
                                        <button
                                            type="button"
                                            className={`${styles.iconBtn}${isHidden ? ` ${styles.iconBtnActive}` : ''}`}
                                            onClick={() => toggleHidden(key)}
                                            title={isHidden ? 'Show value' : 'Hide value'}
                                            aria-pressed={isHidden}
                                            data-testid="memory-hide"
                                        >
                                            <EyeIcon size={13} slashed={isHidden} />
                                        </button>
                                    </td>
                                    <td className={styles.actionCol}>
                                        <button
                                            type="button"
                                            className={styles.iconBtn}
                                            onClick={() => onDelete(key)}
                                            disabled={deleting === key}
                                            title="Forget"
                                            data-testid="memory-delete"
                                        >
                                            {deleting === key ? '…' : <TrashIcon size={13} />}
                                        </button>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            )}
        </div>
    );
}
