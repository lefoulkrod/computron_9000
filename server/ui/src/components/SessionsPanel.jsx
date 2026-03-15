import { useState } from 'react';
import shared from './CustomToolsPanel.module.css';
import styles from './SessionsPanel.module.css';
import TrashIcon from './icons/TrashIcon.jsx';
import useListPanel from '../hooks/useListPanel.js';

function formatTime(isoString) {
    if (!isoString) return '';
    try {
        const d = new Date(isoString);
        const now = new Date();
        const diffMs = now - d;
        const diffMins = Math.floor(diffMs / 60000);
        if (diffMins < 1) return 'just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        const diffHours = Math.floor(diffMins / 60);
        if (diffHours < 24) return `${diffHours}h ago`;
        const diffDays = Math.floor(diffHours / 24);
        return `${diffDays}d ago`;
    } catch (_) {
        return '';
    }
}

export default function SessionsPanel({ onLoadSession }) {
    const {
        items: sessions, loading, collapsed, setCollapsed,
        deleting, handleDelete,
    } = useListPanel('/api/conversations/sessions', {
        startCollapsed: true,
        getId: (s) => s.conversation_id,
    });

    const [resuming, setResuming] = useState(null);

    const handleResume = async (conversationId) => {
        setResuming(conversationId);
        try {
            const ok = await onLoadSession(conversationId);
            if (ok) {
                setCollapsed(true);
            }
        } finally {
            setResuming(null);
        }
    };

    const onDelete = (conversationId) => {
        handleDelete(
            conversationId,
            `/api/conversations/sessions/${conversationId}`,
            (s) => s.conversation_id !== conversationId,
        );
    };

    if (loading || sessions.length === 0) return null;

    return (
        <div className={shared.panel}>
            <div className={shared.header} onClick={() => setCollapsed(c => !c)}>
                <span className={shared.title}>
                    Past Sessions <span className={shared.count}>{sessions.length}</span>
                </span>
                <span className={shared.chevron}>{collapsed ? '▶' : '▼'}</span>
            </div>
            {!collapsed && (
                <ul className={shared.list}>
                    {sessions.map(session => (
                        <li key={session.conversation_id} className={shared.item}>
                            <div className={shared.itemMain}>
                                <span className={shared.name}>
                                    {session.first_message
                                        ? session.first_message.slice(0, 60) + (session.first_message.length > 60 ? '…' : '')
                                        : '(empty)'}
                                </span>
                            </div>
                            <p className={shared.desc}>
                                {session.turn_count} turn{session.turn_count !== 1 ? 's' : ''}
                                {session.started_at ? ` · ${formatTime(session.started_at)}` : ''}
                            </p>
                            <div className={styles.actions}>
                                <button
                                    className={styles.resumeBtn}
                                    onClick={() => handleResume(session.conversation_id)}
                                    disabled={resuming === session.conversation_id}
                                    title="Resume this conversation"
                                >
                                    {resuming === session.conversation_id ? '…' : '↩'}
                                </button>
                                <button
                                    className={shared.deleteBtn}
                                    onClick={() => onDelete(session.conversation_id)}
                                    disabled={deleting === session.conversation_id}
                                    title="Delete this conversation"
                                >
                                    {deleting === session.conversation_id ? '…' : <TrashIcon size={13} />}
                                </button>
                            </div>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}
