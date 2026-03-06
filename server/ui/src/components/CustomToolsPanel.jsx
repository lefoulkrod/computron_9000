import { useState, useEffect, useCallback, useRef } from 'react';
import styles from './CustomToolsPanel.module.css';
import TrashIcon from './icons/TrashIcon.jsx';

function ToolTypeBadge({ type, language }) {
    const label = type === 'command' ? 'cmd' : language || 'bash';
    return <span className={`${styles.badge} ${styles[`badge_${label}`] || styles.badge_bash}`}>{label}</span>;
}

export default function CustomToolsPanel({ refreshSignal, onToolsChanged }) {
    const [tools, setTools] = useState([]);
    const [loading, setLoading] = useState(true);
    const [deleting, setDeleting] = useState(null);
    const [collapsed, setCollapsed] = useState(false);
    const [newToolIds, setNewToolIds] = useState(new Set());
    const prevIdsRef = useRef(new Set());

    const fetchTools = useCallback(async () => {
        try {
            const resp = await fetch('/api/custom-tools');
            if (resp.ok) {
                const fresh = await resp.json();
                const freshIds = new Set(fresh.map(t => t.id));
                const added = fresh.filter(t => !prevIdsRef.current.has(t.id)).map(t => t.id);
                prevIdsRef.current = freshIds;
                if (added.length > 0) {
                    setNewToolIds(new Set(added));
                    setTimeout(() => setNewToolIds(new Set()), 700);
                }
                setTools(fresh);
            }
        } catch (_) {
            // ignore
        } finally {
            setLoading(false);
        }
    }, []);

    // Initial fetch
    useEffect(() => {
        fetchTools();
    }, [fetchTools]);

    // Re-fetch when a tool_created event fires
    useEffect(() => {
        if (refreshSignal > 0) fetchTools();
    }, [refreshSignal, fetchTools]);

    const handleDelete = async (name) => {
        setDeleting(name);
        try {
            const resp = await fetch(`/api/custom-tools/${encodeURIComponent(name)}`, { method: 'DELETE' });
            if (resp.ok || resp.status === 404) {
                setTools(prev => prev.filter(t => t.name !== name));
                if (onToolsChanged) onToolsChanged();
            }
        } catch (_) {
            // ignore
        } finally {
            setDeleting(null);
        }
    };

    if (loading) return null;
    if (tools.length === 0) return null;

    return (
        <div className={styles.panel}>
            <div className={styles.header} onClick={() => setCollapsed(c => !c)}>
                <span className={styles.title}>Custom Tools <span className={styles.count}>{tools.length}</span></span>
                <span className={styles.chevron}>{collapsed ? '▶' : '▼'}</span>
            </div>
            {!collapsed && (
                <ul className={styles.list}>
                    {tools.map(tool => (
                        <li key={tool.id} className={`${styles.item} ${newToolIds.has(tool.id) ? styles.itemNew : ''}`}>
                            <div className={styles.itemMain}>
                                <ToolTypeBadge type={tool.type} language={tool.language} />
                                <span className={styles.name}>{tool.name}</span>
                            </div>
                            <p className={styles.desc}>{tool.description}</p>
                            <button
                                className={styles.deleteBtn}
                                onClick={() => handleDelete(tool.name)}
                                disabled={deleting === tool.name}
                                title="Delete tool"
                            >
                                {deleting === tool.name ? '…' : <TrashIcon size={13} />}
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}
