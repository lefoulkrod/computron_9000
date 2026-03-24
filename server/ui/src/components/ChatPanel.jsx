import React from 'react';
import ChatMessages from './ChatMessages.jsx';
import ChatInput from './ChatInput.jsx';
import ContextUsageBadge from './ContextUsageBadge.jsx';
import { formatAgentName } from './AgentCard.jsx';
import styles from './ChatPanel.module.css';

/**
 * Chat panel for talking to the root agent. Shows the agent name and
 * context usage in the header (from the agent reducer), the scrollable
 * message list, and the input bar.
 */
export default function ChatPanel({ messages, onSend, onStop, isStreaming, attachment, onPreview, rootAgent }) {
    return (
        <div className={styles.panel}>
            <div className={styles.header}>
                {rootAgent?.name ? (
                    <span className={styles.agentName}>{formatAgentName(rootAgent.name)}</span>
                ) : (
                    <span>Chat</span>
                )}
                <ContextUsageBadge contextUsage={rootAgent?.contextUsage} />
            </div>
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
