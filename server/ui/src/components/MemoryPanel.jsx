import { useState, useCallback } from 'react';
import styles from './CustomToolsPanel.module.css';
import TrashIcon from './icons/TrashIcon.jsx';
import EyeIcon from './icons/EyeIcon.jsx';
import useListPanel from '../hooks/useListPanel.js';

export default function MemoryPanel({ refreshSignal }) {
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
                headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                body: JSON.stringify({ hidden: nowHidden }),
            });
        } catch (_) {
            // revert on error
            setHiddenKeys((prev) => {
                const next = new Set(prev);
                if (nowHidden) next.delete(key); else next.add(key);
                return next;
            });
        }
    };

    if (loading || entries.length === 0) return null;

    return (
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
                                onClick={() => onDelete(key)}
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
    );
}
