import React, { useEffect, useRef } from 'react';
import Message from './Message.jsx';
import styles from './ChatMessages.module.css';

export default function ChatMessages({ messages, showSubAgents = true, onPreview }) {
    const containerRef = useRef(null);
    const endRef = useRef(null);

    useEffect(() => {
        const el = containerRef.current;
        if (!el) return;
        // Only auto-scroll if the user is near the bottom (within 150px).
        // This prevents hijacking manual scroll-back during streaming.
        const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 150;
        if (nearBottom) {
            el.scrollTop = el.scrollHeight;
        }
    }, [messages]);

    // Filter messages based on showSubAgents toggle
    const visibleMessages = showSubAgents
        ? messages
        : messages.filter((msg) => msg.role === 'user' || (msg.role === 'assistant' && (msg.depth === 0 || msg.depth === undefined)));

    return (
        <div className={styles.chatMessages} id="chatMessages" ref={containerRef}>
            {visibleMessages.map((msg, idx) => (
                <Message key={msg.id || idx} {...msg} showSubAgents={showSubAgents} onPreview={onPreview} />
            ))}
            <div ref={endRef} />
        </div>
    );
}
