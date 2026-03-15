import styles from './CustomToolsPanel.module.css';
import TrashIcon from './icons/TrashIcon.jsx';
import useListPanel from '../hooks/useListPanel.js';

function ToolTypeBadge({ type, language }) {
    const label = type === 'command' ? 'cmd' : language || 'bash';
    return <span className={`${styles.badge} ${styles[`badge_${label}`] || styles.badge_bash}`}>{label}</span>;
}

export default function CustomToolsPanel({ refreshSignal, onToolsChanged }) {
    const {
        items: tools, loading, collapsed, setCollapsed,
        deleting, handleDelete, newItemIds,
    } = useListPanel('/api/custom-tools', { refreshSignal });

    const onDelete = async (name) => {
        await handleDelete(
            name,
            `/api/custom-tools/${encodeURIComponent(name)}`,
            (t) => t.name !== name,
        );
        if (onToolsChanged) onToolsChanged();
    };

    if (loading || tools.length === 0) return null;

    return (
        <div className={styles.panel}>
            <div className={styles.header} onClick={() => setCollapsed(c => !c)}>
                <span className={styles.title}>Custom Tools <span className={styles.count}>{tools.length}</span></span>
                <span className={styles.chevron}>{collapsed ? '▶' : '▼'}</span>
            </div>
            {!collapsed && (
                <ul className={styles.list}>
                    {tools.map(tool => (
                        <li key={tool.id} className={`${styles.item} ${newItemIds.has(tool.id) ? styles.itemNew : ''}`}>
                            <div className={styles.itemMain}>
                                <ToolTypeBadge type={tool.type} language={tool.language} />
                                <span className={styles.name}>{tool.name}</span>
                            </div>
                            <p className={styles.desc}>{tool.description}</p>
                            <button
                                className={styles.deleteBtn}
                                onClick={() => onDelete(tool.name)}
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
