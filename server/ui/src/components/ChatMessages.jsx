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
    const { agents } = useAgentState();
    const { ref, onScroll } = useAutoScroll([messages]);

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
