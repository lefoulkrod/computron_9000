import React from 'react';
import ChatMessages from './ChatMessages.jsx';
import ChatInput from './ChatInput.jsx';
import ContextUsageBadge from './ContextUsageBadge.jsx';
import { formatAgentName } from './AgentCard.jsx';
import styles from './ChatPanel.module.css';

/**
 * Chat panel for talking to the root agent. Shows the agent name and
 * context usage in the header (pulled from the latest assistant message),
 * the scrollable message list, and the input bar.
 */
export default function ChatPanel({ messages, onSend, onStop, isStreaming, attachment, onPreview }) {
    const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant' && !m.placeholder);
    const agentName = lastAssistant?.agent_name;
    const contextUsage = lastAssistant?.contextUsage;

    return (
        <div className={styles.panel}>
            <div className={styles.header}>
                {agentName ? (
                    <span className={styles.agentName}>{formatAgentName(agentName)}</span>
                ) : (
                    <span>Chat</span>
                )}
                <ContextUsageBadge contextUsage={contextUsage} />
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
