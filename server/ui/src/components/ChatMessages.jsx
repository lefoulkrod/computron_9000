import Message from './Message.jsx';
import useAutoScroll from '../hooks/useAutoScroll.js';
import styles from './ChatMessages.module.css';

/**
 * Scrollable message list. Sticks to the bottom as new text arrives,
 * but stops auto-scrolling if the user scrolls up.
 */
export default function ChatMessages({ messages, onPreview }) {
    const { ref, onScroll } = useAutoScroll([messages]);

    return (
        <div className={styles.chatMessages} id="chatMessages" ref={ref} onScroll={onScroll}>
            {messages.map((msg, idx) => (
                <Message key={msg.id || idx} {...msg} onPreview={onPreview} />
            ))}
            <div />
        </div>
    );
}
