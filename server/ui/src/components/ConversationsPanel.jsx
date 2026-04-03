import { useState } from 'react';
import shared from './CustomToolsPanel.module.css';
import styles from './ConversationsPanel.module.css';
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

export default function ConversationsPanel({ onLoadConversation }) {
    const {
        items: conversations, loading,
        deleting, handleDelete,
    } = useListPanel('/api/conversations/sessions', {
        getId: (s) => s.conversation_id,
    });

    const [resuming, setResuming] = useState(null);

    const handleResume = async (conversationId) => {
        setResuming(conversationId);
        try {
            await onLoadConversation(conversationId);
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

    if (loading || conversations.length === 0) return null;

    return (
        <ul className={shared.list}>
            {conversations.map(convo => (
                <li key={convo.conversation_id} className={shared.item}>
                    <div className={shared.itemMain}>
                        <span className={shared.name}>
                            {convo.title
                                ? convo.title.slice(0, 60) + (convo.title.length > 60 ? '…' : '')
                                : convo.first_message
                                    ? convo.first_message.slice(0, 60) + (convo.first_message.length > 60 ? '…' : '')
                                    : '(empty)'}
                        </span>
                    </div>
                    <p className={shared.desc}>
                        {convo.turn_count} turn{convo.turn_count !== 1 ? 's' : ''}
                        {convo.started_at ? ` · ${formatTime(convo.started_at)}` : ''}
                    </p>
                    <div className={styles.actions}>
                        <button
                            className={styles.resumeBtn}
                            onClick={() => handleResume(convo.conversation_id)}
                            disabled={resuming === convo.conversation_id}
                            title="Resume this conversation"
                        >
                            {resuming === convo.conversation_id ? '…' : '↩'}
                        </button>
                        <button
                            className={shared.deleteBtn}
                            onClick={() => onDelete(convo.conversation_id)}
                            disabled={deleting === convo.conversation_id}
                            title="Delete this conversation"
                        >
                            {deleting === convo.conversation_id ? '…' : <TrashIcon size={13} />}
                        </button>
                    </div>
                </li>
            ))}
        </ul>
    );
}
