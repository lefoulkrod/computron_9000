import React, { useEffect, useRef } from 'react';
import Message from './Message.jsx';
import styles from './ChatMessages.module.css';

export default function ChatMessages({ messages }) {
    const containerRef = useRef(null);

    useEffect(() => {
        const el = containerRef.current;
        if (!el) return;
        el.scrollTop = el.scrollHeight;
    }, [messages]);

    return (
        <div className={styles.chatMessages} id="chatMessages" ref={containerRef}>
            {messages.map((msg, idx) => (
                <Message key={msg.id || idx} {...msg} />
            ))}
        </div>
    );
}
