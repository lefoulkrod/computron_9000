import Message from './Message.jsx';
import useAutoScroll from '../hooks/useAutoScroll.js';
import styles from './ChatMessages.module.css';

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
