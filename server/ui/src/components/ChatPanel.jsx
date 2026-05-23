import React, { useState, useCallback } from 'react';
import ChatMessages from './ChatMessages.jsx';
import ChatInput from './ChatInput.jsx';
import ContextMeter from './ContextMeter.jsx';
import { formatAgentName } from './AgentCard.jsx';
import StatusDot from './StatusDot.jsx';
import styles from './ChatPanel.module.css';

/**
 * Chat panel for talking to the root agent. A title bar across the top
 * carries the conversation title, turn count, and context meter; below
 * it the scrollable message list and the input bar.
 *
 * When sub-agents have been spawned, a network indicator appears in the
 * title bar so the user can navigate to the full agent network view.
 */
export default function ChatPanel({ messages, onSend, onStop, isStreaming, attachment, onPreview, onSelectAgent, rootAgent, networkActivated, networkAgentCount, networkRunningCount, onOpenNetwork, selectedProfileId, onProfileChange, profileRefreshSignal }) {
    const [draft, setDraft] = useState('');
    const clearDraft = useCallback(() => setDraft(''), []);

    // A turn is one user message and its response. Title falls back to the
    // agent name until the live conversation title is wired up.
    const turnCount = messages.filter((m) => m.role === 'user').length;
    const title = rootAgent?.name ? formatAgentName(rootAgent.name) : 'Chat';

    return (
        <div className={styles.panel}>
            <div className={styles.titleBar} data-testid="chat-title-bar">
                <span className={styles.title} data-testid="chat-title">{title}</span>
                {turnCount > 0 && (
                    <span className={styles.turns} data-testid="chat-turns">
                        {turnCount} turn{turnCount !== 1 ? 's' : ''}
                    </span>
                )}
                <ContextMeter contextUsage={rootAgent?.contextUsage} />
                <span className={styles.spacer} />
                {networkActivated && (
                    <button className={styles.networkBtn} onClick={onOpenNetwork} title="Open agent network view" data-testid="network-indicator">
                        <StatusDot status={networkRunningCount > 0 ? 'running' : 'complete'} />
                        <span>{networkAgentCount} agent{networkAgentCount !== 1 ? 's' : ''}</span>
                    </button>
                )}
            </div>
            <ChatMessages messages={messages} onPreview={onPreview} onSelectAgent={onSelectAgent} onStarterSelect={setDraft} />
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
