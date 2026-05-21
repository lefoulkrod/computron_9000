import { useMemo, useState } from 'react';
import useListPanel from '../hooks/useListPanel.js';
import TrashIcon from './icons/TrashIcon.jsx';
import styles from './RecentConversations.module.css';

const BUCKET_ORDER = ['Today', 'Yesterday', 'Earlier'];

/** Bucket a conversation's start time into Today / Yesterday / Earlier. */
function _dayBucket(iso) {
    if (!iso) return 'Earlier';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return 'Earlier';
    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const startOfYesterday = new Date(startOfToday);
    startOfYesterday.setDate(startOfYesterday.getDate() - 1);
    if (d >= startOfToday) return 'Today';
    if (d >= startOfYesterday) return 'Yesterday';
    return 'Earlier';
}

function _label(convo) {
    return convo.title || convo.first_message || '(empty)';
}

/**
 * Inline list of recent conversations for the sidebar: a search box
 * over a day-grouped, scrollable list. Clicking a row loads that
 * conversation; a hover delete removes it.
 */
export default function RecentConversations({ onLoadConversation, activeConversationId, refreshSignal = 0 }) {
    const { items, loading, deleting, handleDelete } = useListPanel(
        '/api/conversations/sessions',
        { getId: (s) => s.conversation_id, refreshSignal },
    );
    const [query, setQuery] = useState('');

    const groups = useMemo(() => {
        const q = query.trim().toLowerCase();
        const filtered = q
            ? items.filter((c) => _label(c).toLowerCase().includes(q))
            : items;
        const byBucket = new Map();
        for (const convo of filtered) {
            const bucket = _dayBucket(convo.started_at);
            if (!byBucket.has(bucket)) byBucket.set(bucket, []);
            byBucket.get(bucket).push(convo);
        }
        return BUCKET_ORDER
            .filter((b) => byBucket.has(b))
            .map((b) => ({ bucket: b, items: byBucket.get(b) }));
    }, [items, query]);

    const onDelete = (e, conversationId) => {
        e.stopPropagation();
        handleDelete(
            conversationId,
            `/api/conversations/sessions/${conversationId}`,
            (s) => s.conversation_id !== conversationId,
        );
    };

    return (
        <div className={styles.recent} data-testid="recent-conversations">
            <div className={styles.search}>
                <i className="bi bi-search" />
                <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Search conversations…"
                    aria-label="Search conversations"
                    data-testid="recent-search"
                />
            </div>

            <div className={styles.list}>
                {!loading && groups.length === 0 && (
                    <div className={styles.empty} data-testid="recent-empty">
                        {query ? `No matches for "${query}"` : 'No conversations yet'}
                    </div>
                )}
                {groups.map(({ bucket, items: convos }) => (
                    <div key={bucket}>
                        <div className={styles.dayLabel}>{bucket}</div>
                        {convos.map((convo) => {
                            const id = convo.conversation_id;
                            const active = id === activeConversationId;
                            return (
                                <div
                                    key={id}
                                    className={`${styles.item} ${active ? styles.active : ''}`}
                                    onClick={() => onLoadConversation(id)}
                                    role="button"
                                    tabIndex={0}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter' || e.key === ' ') {
                                            e.preventDefault();
                                            onLoadConversation(id);
                                        }
                                    }}
                                    title={_label(convo)}
                                    data-testid="recent-item"
                                    data-conversation-id={id}
                                >
                                    <span className={styles.itemTitle}>{_label(convo)}</span>
                                    <button
                                        className={styles.deleteBtn}
                                        onClick={(e) => onDelete(e, id)}
                                        disabled={deleting === id}
                                        title="Delete conversation"
                                        aria-label="Delete conversation"
                                        data-testid="recent-delete"
                                    >
                                        {deleting === id ? '…' : <TrashIcon size={12} />}
                                    </button>
                                </div>
                            );
                        })}
                    </div>
                ))}
            </div>
        </div>
    );
}
