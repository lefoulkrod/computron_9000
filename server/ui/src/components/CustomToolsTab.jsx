import TrashIcon from './icons/TrashIcon.jsx';
import useListPanel from '../hooks/useListPanel.js';
import styles from './CustomToolsTab.module.css';

function _badgeLabel(tool) {
    if (tool?.type === 'command') return 'cmd';
    return tool?.language || 'bash';
}

function _badgeClass(label) {
    if (label === 'cmd') return styles.badgeCmd;
    if (label === 'python') return styles.badgePython;
    return styles.badgeBash;
}

/**
 * Custom Tools tab inside Settings. Compact one-row-per-tool table:
 * type badge, name, description, delete. Visible only when the feature
 * flag is on (the tab registry filters by features.custom_tools).
 */
export default function CustomToolsTab({ refreshSignal }) {
    const {
        items: tools, loading,
        deleting, handleDelete,
    } = useListPanel('/api/custom-tools', { refreshSignal });

    const onDelete = (name) => {
        handleDelete(name, `/api/custom-tools/${encodeURIComponent(name)}`, (t) => t.name !== name);
    };

    return (
        <div className={styles.tab} data-testid="custom-tools-tab">
            <div className={styles.header}>
                <span className={styles.title}>Custom Tools</span>
                <span className={styles.count} data-testid="custom-tools-count">
                    {loading ? '' : `${tools.length} ${tools.length === 1 ? 'tool' : 'tools'}`}
                </span>
            </div>
            {loading && <p className={styles.empty}>Loading…</p>}
            {!loading && tools.length === 0 && (
                <p className={styles.empty}>No custom tools defined.</p>
            )}
            {!loading && tools.length > 0 && (
                <table className={styles.table}>
                    <thead>
                        <tr>
                            <th className={styles.typeCol}>Type</th>
                            <th className={styles.nameCol}>Name</th>
                            <th className={styles.descCol}>Description</th>
                            <th className={styles.actionCol}></th>
                        </tr>
                    </thead>
                    <tbody>
                        {tools.map((tool) => {
                            const label = _badgeLabel(tool);
                            return (
                                <tr key={tool.id} data-testid="custom-tools-row" data-tool-name={tool.name}>
                                    <td className={styles.typeCol}>
                                        <span className={`${styles.badge} ${_badgeClass(label)}`}>{label}</span>
                                    </td>
                                    <td className={styles.name}>{tool.name}</td>
                                    <td className={styles.desc} title={tool.description}>{tool.description}</td>
                                    <td className={styles.actionCol}>
                                        <button
                                            type="button"
                                            className={styles.iconBtn}
                                            onClick={() => onDelete(tool.name)}
                                            disabled={deleting === tool.name}
                                            title="Delete tool"
                                            data-testid="custom-tools-delete"
                                        >
                                            {deleting === tool.name ? '…' : <TrashIcon size={13} />}
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
