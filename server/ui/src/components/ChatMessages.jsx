import Message from './Message.jsx';
import useAutoScroll from '../hooks/useAutoScroll.js';
import { useAgentState } from '../hooks/useAgentState.jsx';
import styles from './ChatMessages.module.css';

/**
 * Scrollable message list. Sticks to the bottom as new text arrives,
 * but stops auto-scrolling if the user scrolls up.
 *
 * Assistant message content comes from the agent reducer's activityLog
 * (same source as the activity view). Falls back to msg.entries for
 * loaded conversation history where no agent state exists.
 */
export default function ChatMessages({ messages, onPreview }) {
    const { agents, rootId } = useAgentState();
    // Scroll when messages change OR when the root agent's content grows.
    // We track the last entry's text length so scroll fires as tokens
    // stream in, not just when new entries are added.
    const rootLog = rootId ? agents[rootId]?.activityLog : null;
    const lastEntry = rootLog?.length ? rootLog[rootLog.length - 1] : null;
    const scrollKey = lastEntry ? (lastEntry.content?.length || lastEntry.thinking?.length || 0) : 0;
    const { ref, onScroll } = useAutoScroll([messages, rootLog?.length, scrollKey]);

    return (
        <div className={styles.chatMessages} id="chatMessages" ref={ref} onScroll={onScroll}>
            {messages.map((msg, idx) => {
                if (msg.role === 'assistant' && msg.agentId) {
                    const entries = agents[msg.agentId]?.activityLog;
                    return <Message key={msg.id || idx} {...msg} entries={entries} onPreview={onPreview} />;
                }
                return <Message key={msg.id || idx} {...msg} onPreview={onPreview} />;
            })}
            <div />
        </div>
    );
}
