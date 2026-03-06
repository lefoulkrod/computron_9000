import { useState, useEffect, useCallback } from 'react';
import styles from './CustomToolsPanel.module.css';
import TrashIcon from './icons/TrashIcon.jsx';
import EyeIcon from './icons/EyeIcon.jsx';

export default function MemoryPanel({ refreshSignal }) {
    const [entries, setEntries] = useState([]);
    const [hiddenKeys, setHiddenKeys] = useState(new Set());
    const [loading, setLoading] = useState(true);
    const [deleting, setDeleting] = useState(null);
    const [collapsed, setCollapsed] = useState(false);

    const fetchMemory = useCallback(async () => {
        try {
            const resp = await fetch('/api/memory');
            if (resp.ok) {
                const data = await resp.json();
                setEntries(Object.entries(data.entries));
                setHiddenKeys(new Set(data.hidden));
            }
        } catch (_) {
            // ignore
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchMemory(); }, [fetchMemory]);
    useEffect(() => { if (refreshSignal > 0) fetchMemory(); }, [refreshSignal, fetchMemory]);

    const handleDelete = async (key) => {
        setDeleting(key);
        try {
            const resp = await fetch(`/api/memory/${encodeURIComponent(key)}`, { method: 'DELETE' });
            if (resp.ok || resp.status === 404) {
                setEntries(prev => prev.filter(([k]) => k !== key));
                setHiddenKeys(prev => { const next = new Set(prev); next.delete(key); return next; });
            }
        } catch (_) {
            // ignore
        } finally {
            setDeleting(null);
        }
    };

    const toggleHidden = async (key) => {
        const nowHidden = !hiddenKeys.has(key);
        // optimistic update
        setHiddenKeys(prev => {
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
            // revert on error
            setHiddenKeys(prev => {
                const next = new Set(prev);
                if (nowHidden) next.delete(key); else next.add(key);
                return next;
            });
        }
    };

    if (loading || entries.length === 0) return null;

    return (
        <div className={styles.panel}>
            <div className={styles.header} onClick={() => setCollapsed(c => !c)}>
                <span className={styles.title}>Memory <span className={styles.count}>{entries.length}</span></span>
                <span className={styles.chevron}>{collapsed ? '▶' : '▼'}</span>
            </div>
            {!collapsed && (
                <ul className={styles.list}>
                    {entries.map(([key, value]) => {
                        const isHidden = hiddenKeys.has(key);
                        return (
                            <li key={key} className={styles.item}>
                                <div className={styles.itemMain}>
                                    <span className={styles.name}>{key}</span>
                                </div>
                                <p className={styles.desc} title={isHidden ? undefined : value}>
                                    {isHidden ? '••••••••' : value}
                                </p>
                                <div className={styles.itemActions}>
                                    <button
                                        className={`${styles.eyeBtn}${isHidden ? ` ${styles.eyeBtnActive}` : ''}`}
                                        onClick={() => toggleHidden(key)}
                                        title={isHidden ? 'Show value' : 'Hide value'}
                                    >
                                        <EyeIcon size={12} slashed={isHidden} />
                                    </button>
                                    <button
                                        className={styles.deleteBtn}
                                        onClick={() => handleDelete(key)}
                                        disabled={deleting === key}
                                        title="Forget"
                                    >
                                        {deleting === key ? '…' : <TrashIcon size={13} />}
                                    </button>
                                </div>
                            </li>
                        );
                    })}
                </ul>
            )}
        </div>
    );
}
