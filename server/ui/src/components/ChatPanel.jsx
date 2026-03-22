import React from 'react';
import ChatMessages from './ChatMessages.jsx';
import ChatInput from './ChatInput.jsx';
import styles from './ChatPanel.module.css';

export default function ChatPanel({ messages, onSend, onStop, isStreaming, attachment, onPreview }) {
    return (
        <div className={styles.panel}>
            <div className={styles.header}>Chat</div>
            <ChatMessages messages={messages} onPreview={onPreview} />
            <ChatInput
                onSend={onSend}
                onStop={onStop}
                isStreaming={isStreaming}
                attachment={attachment}
            />
        </div>
    );
}
