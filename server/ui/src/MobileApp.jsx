import { useState, useRef, useCallback } from 'react';

import Header from './components/Header.jsx';
import ChatInput from './components/ChatInput.jsx';
import ChatMessages from './components/ChatMessages.jsx';
import MobileSettingsDrawer from './components/MobileSettingsDrawer.jsx';
import useModelSettings from './hooks/useModelSettings.js';
import useStreamingChat from './hooks/useStreamingChat.js';
import { useToast } from './components/ToastProvider.jsx';
import styles from './MobileApp.module.css';

// No-op callbacks — events still fire from the stream but we don't track
// panel state (browser previews, terminal, desktop, etc.) on mobile.
const _noop = () => {};

export default function MobileApp({ dark, onToggleTheme }) {
    const [drawerOpen, setDrawerOpen] = useState(false);

    const modelSettings = useModelSettings();
    const { addToast } = useToast();

    const _stableCallbacks = useRef({
        onBrowserSnapshot: _noop,
        onTerminalOutput: _noop,
        onToolCreated: _noop,
        onMemoryChanged: _noop,
        onAudioPlayback: _noop,
        onNudgeSent: _noop,
        onSkillApplied: (event) => addToast(`Using skill: ${event.skill_name}`, { type: 'info', duration: 4000 }),
        onDesktopActive: _noop,
        onGenerationPreview: _noop,
    }).current;

    const {
        messages,
        isStreaming,
        sendMessage,
        stopGeneration,
        loadSession,
        newSession: chatNewSession,
    } = useStreamingChat(_stableCallbacks);

    const handleSend = useCallback((message, fileData, agent) => {
        sendMessage(message, fileData, modelSettings, agent);
    }, [sendMessage, modelSettings]);

    const newSession = useCallback(async () => {
        await chatNewSession();
    }, [chatNewSession]);

    return (
        <div className={styles.mobileLayout}>
            <Header
                dark={dark}
                onToggleTheme={onToggleTheme}
                onNewSession={newSession}
                compact
                onOpenSettings={() => setDrawerOpen(true)}
            />
            <div className={styles.messageArea}>
                <ChatMessages
                    messages={messages}
                    showSubAgents={true}
                />
            </div>
            <div className={styles.inputBar}>
                <ChatInput
                    onSend={handleSend}
                    onStop={stopGeneration}
                    isStreaming={isStreaming}
                    compact
                />
            </div>
            <MobileSettingsDrawer
                open={drawerOpen}
                onClose={() => setDrawerOpen(false)}
                modelSettings={modelSettings}
                isStreaming={isStreaming}
                onLoadSession={loadSession}
            />
        </div>
    );
}
