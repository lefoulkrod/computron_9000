import React, { useEffect, useRef } from 'react';
import Message from './Message.jsx';
import styles from './ChatMessages.module.css';

export default function ChatMessages({ messages, showSubAgents = true }) {
    const containerRef = useRef(null);
    const endRef = useRef(null);

    useEffect(() => {
        // Smoothly ensure the latest message is visible inside the scroll container
        const el = containerRef.current;
        if (!el) return;
        // Fallback direct scroll
        el.scrollTop = el.scrollHeight;
        // Also ask the last sentinel to scroll into view (more reliable with images/renders)
        if (endRef.current && endRef.current.scrollIntoView) {
            endRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
        }
    }, [messages]);

    // Filter messages based on showSubAgents toggle
    const visibleMessages = showSubAgents
        ? messages
        : messages.filter((msg) => msg.role === 'user' || (msg.role === 'assistant' && (msg.depth === 0 || msg.depth === undefined)));

    return (
        <div className={styles.chatMessages} id="chatMessages" ref={containerRef}>
            {visibleMessages.map((msg, idx) => (
                <Message key={msg.id || idx} {...msg} showSubAgents={showSubAgents} />
            ))}
            <div ref={endRef} />
        </div>
    );
}
