import React, { useState, useCallback } from 'react';
import ChatMessages from './ChatMessages.jsx';
import ChatInput from './ChatInput.jsx';
import ContextUsageBadge from './ContextUsageBadge.jsx';
import { formatAgentName } from './AgentCard.jsx';
import styles from './ChatPanel.module.css';

/**
 * Chat panel for talking to the root agent. Shows the agent name and
 * context usage in the header (from the agent reducer), the scrollable
 * message list, and the input bar.
 *
 * When sub-agents have been spawned, a network indicator appears in the
 * header so the user can navigate to the full agent network view.
 */
export default function ChatPanel({ messages, onSend, onStop, isStreaming, attachment, onPreview, rootAgent, networkActivated, networkAgentCount, networkRunningCount, onOpenNetwork, selectedProfileId, onProfileChange, profileRefreshSignal }) {
    const [draft, setDraft] = useState('');
    const clearDraft = useCallback(() => setDraft(''), []);

    return (
        <div className={styles.panel}>
            <div className={styles.header}>
                {rootAgent?.name ? (
                    <span className={styles.agentName}>{formatAgentName(rootAgent.name)}</span>
                ) : (
                    <span>Chat</span>
                )}
                <ContextUsageBadge contextUsage={rootAgent?.contextUsage} />
                {networkActivated && (
                    <button className={styles.networkBtn} onClick={onOpenNetwork} title="Open agent network view">
                        <span className={`${styles.networkDot} ${networkRunningCount > 0 ? styles.networkDotActive : ''}`} />
                        <span>{networkAgentCount} agent{networkAgentCount !== 1 ? 's' : ''}</span>
                    </button>
                )}
            </div>
            <ChatMessages messages={messages} onPreview={onPreview} onStarterSelect={setDraft} />
            <ChatInput
                onSend={onSend}
                onStop={onStop}
                isStreaming={isStreaming}
                attachment={attachment}
                draft={draft}
                onDraftConsumed={clearDraft}
                selectedProfileId={selectedProfileId}
                onProfileChange={onProfileChange}
                profileRefreshSignal={profileRefreshSignal}
            />
        </div>
    );
}
