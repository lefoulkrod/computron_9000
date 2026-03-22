import { useState, useEffect, useRef, useCallback } from 'react';

import Header from './components/Header.jsx';
import ChatPanel from './components/ChatPanel.jsx';
import BrowserPreview from './components/BrowserPreview.jsx';
import DesktopPreview from './components/DesktopPreview.jsx';
import FilePreview from './components/FilePreview.jsx';
import CustomToolsPanel from './components/CustomToolsPanel.jsx';
import ConversationsPanel from './components/ConversationsPanel.jsx';
import MemoryPanel from './components/MemoryPanel.jsx';
import ModelSettingsPanel from './components/ModelSettingsPanel.jsx';
import TerminalPanel from './components/TerminalOutput.jsx';
import GenerationPreview from './components/GenerationPreview.jsx';
import AgentNetwork from './components/AgentNetwork.jsx';
import AgentActivityView from './components/AgentActivityView.jsx';
import Sidebar from './components/Sidebar.jsx';
import FlyoutPanel from './components/FlyoutPanel.jsx';
import useModelSettings from './hooks/useModelSettings.js';
import useStreamingChat from './hooks/useStreamingChat.js';
import { mergeTerminalEvent } from './utils/agentUtils.js';
import { AgentStateProvider, useAgentState, useAgentDispatch, hasSubAgents } from './hooks/useAgentState.jsx';
import { useToast } from './components/ToastProvider.jsx';
import styles from './App.module.css';

function _reopenPanel(name) {
    return (prev) => {
        if (!prev.has(name)) return prev;
        const next = new Set(prev);
        next.delete(name);
        return next;
    };
}

function _closePanel(name) {
    return (prev) => new Set(prev).add(name);
}

function DesktopAppInner({ dark, onToggleTheme }) {
    const agentDispatch = useAgentDispatch();
    const [browserSnapshot, setBrowserSnapshot] = useState(null);
    const [filePreview, setFilePreview] = useState(null);
    const [attachment, setAttachment] = useState(null);
    const [flyoutPanel, setFlyoutPanel] = useState(null);
    const [toolsPanelKey, setToolsPanelKey] = useState(0);
    const [memoryRefreshSignal, setMemoryRefreshSignal] = useState(0);
    const [toolsRefreshSignal, setToolsRefreshSignal] = useState(0);
    const [pendingAudio, setPendingAudio] = useState(null);
    const [muted, setMuted] = useState(false);
    const [terminalLines, setTerminalLines] = useState([]);
    const [generationPreview, setGenerationPreview] = useState(null);
    const [desktopActive, setDesktopActive] = useState(false);
    // Skills panel removed — skill extraction dropped in multi-agent overhaul
    const [closedPanels, setClosedPanels] = useState(new Set());
    const [nudgeToast, setNudgeToast] = useState(null);

    const modelSettings = useModelSettings();
    const { addToast } = useToast();

    const _streamCallbacksRef = useRef(null);
    _streamCallbacksRef.current = {
        onBrowserSnapshot: (snapshot) => {
            // Update global state (backward compat for simple chat)
            setBrowserSnapshot(snapshot);
            setClosedPanels(_reopenPanel('browser'));
            // Update per-agent state
            if (snapshot.agentId) {
                agentDispatch({ type: 'UPDATE_BROWSER_SNAPSHOT', agentId: snapshot.agentId, snapshot });
            }
        },
        onTerminalOutput: (event) => {
            // Update global state
            setTerminalLines((prev) => mergeTerminalEvent(prev, event));
            setClosedPanels(_reopenPanel('terminal'));
            // Update per-agent state
            if (event.agentId) {
                agentDispatch({ type: 'UPDATE_TERMINAL', agentId: event.agentId, event });
            }
        },
        onToolCreated: () => setToolsRefreshSignal((s) => s + 1),
        onMemoryChanged: () => setMemoryRefreshSignal((s) => s + 1),
        onAudioPlayback: (audio) => setPendingAudio(audio),
        onNudgeSent: (text) => setNudgeToast(text || 'Nudge sent'),
        onDesktopActive: (agentId) => {
            setDesktopActive(true);
            setClosedPanels(_reopenPanel('desktop'));
            if (agentId) {
                agentDispatch({ type: 'UPDATE_DESKTOP_ACTIVE', agentId });
            }
        },
        onGenerationPreview: (event) => {
            setGenerationPreview((prev) => {
                if (!prev || prev.gen_id !== event.gen_id) return event;
                return { ...prev, ...event };
            });
            setClosedPanels((prev) => {
                if (!prev.has('generation') && prev.has('file')) return prev;
                const next = new Set(prev);
                next.delete('generation');
                next.add('file');
                return next;
            });
            if (event.agentId) {
                agentDispatch({ type: 'UPDATE_GENERATION_PREVIEW', agentId: event.agentId, preview: event });
            }
        },
        // Agent lifecycle events
        onAgentEvent: (event) => {
            if (event.type === 'agent_started') {
                agentDispatch({
                    type: 'AGENT_STARTED',
                    agentId: event.agent_id,
                    agentName: event.agent_name,
                    parentAgentId: event.parent_agent_id || null,
                    instruction: event.instruction,
                    timestamp: Date.now(),
                });
            } else if (event.type === 'agent_completed') {
                agentDispatch({
                    type: 'AGENT_COMPLETED',
                    agentId: event.agent_id,
                    status: event.status,
                });
            }
        },
        // Agent tool call events
        onAgentToolCall: ({ name, agentId }) => {
            if (agentId) {
                agentDispatch({ type: 'UPDATE_ACTIVE_TOOL', agentId, toolName: name });
                agentDispatch({
                    type: 'APPEND_ACTIVITY',
                    agentId,
                    entry: { type: 'tool_call', name, timestamp: Date.now() },
                });
            }
        },
        // Sub-agent streaming content/thinking
        onAgentContent: ({ agentId, content, thinking }) => {
            if (content) {
                agentDispatch({
                    type: 'APPEND_ACTIVITY',
                    agentId,
                    entry: { type: 'content', content, timestamp: Date.now() },
                });
                agentDispatch({ type: 'UPDATE_CONTENT_SNIPPET', agentId, content });
            }
            if (thinking) {
                agentDispatch({
                    type: 'APPEND_ACTIVITY',
                    agentId,
                    entry: { type: 'thinking', thinking, timestamp: Date.now() },
                });
            }
        },
        // Agent context usage (iteration info)
        onAgentContextUsage: ({ agentId, iteration, maxIterations }) => {
            agentDispatch({ type: 'UPDATE_ITERATION', agentId, iteration, maxIterations });
        },
        // Agent file output
        onAgentFileOutput: ({ agentId, ...fileEvent }) => {
            if (agentId) {
                agentDispatch({
                    type: 'APPEND_ACTIVITY',
                    agentId,
                    entry: { type: 'file_output', ...fileEvent, timestamp: Date.now() },
                });
            }
        },
    };
    const _stableCallbacks = useRef({
        onBrowserSnapshot: (...args) => _streamCallbacksRef.current.onBrowserSnapshot(...args),
        onTerminalOutput: (...args) => _streamCallbacksRef.current.onTerminalOutput(...args),
        onToolCreated: (...args) => _streamCallbacksRef.current.onToolCreated(...args),
        onMemoryChanged: (...args) => _streamCallbacksRef.current.onMemoryChanged(...args),
        onAudioPlayback: (...args) => _streamCallbacksRef.current.onAudioPlayback(...args),
        onNudgeSent: (...args) => _streamCallbacksRef.current.onNudgeSent(...args),
        onDesktopActive: (...args) => _streamCallbacksRef.current.onDesktopActive(...args),
        onGenerationPreview: (...args) => _streamCallbacksRef.current.onGenerationPreview(...args),
        onAgentEvent: (...args) => _streamCallbacksRef.current.onAgentEvent(...args),
        onAgentToolCall: (...args) => _streamCallbacksRef.current.onAgentToolCall(...args),
        onAgentContent: (...args) => _streamCallbacksRef.current.onAgentContent(...args),
        onAgentContextUsage: (...args) => _streamCallbacksRef.current.onAgentContextUsage(...args),
        onAgentFileOutput: (...args) => _streamCallbacksRef.current.onAgentFileOutput(...args),
    }).current;

    const {
        messages,
        isStreaming,
        sendMessage,
        stopGeneration,
        loadConversation,
        newConversation: chatNewConversation,
    } = useStreamingChat(_stableCallbacks);

    useEffect(() => {
        if (!nudgeToast) return;
        const timer = setTimeout(() => setNudgeToast(null), 3000);
        return () => clearTimeout(timer);
    }, [nudgeToast]);

    const handleAttachScreenshot = (base64Screenshot) => {
        setAttachment({ base64: base64Screenshot, contentType: 'image/png' });
    };

    const handleSend = useCallback((message, fileData, agent) => {
        setAttachment(null);
        sendMessage(message, fileData, modelSettings, agent);
    }, [sendMessage, modelSettings]);

    const openDesktop = useCallback(async () => {
        if (desktopActive && !closedPanels.has('desktop')) return;
        try {
            const res = await fetch('/api/desktop/start', { method: 'POST' });
            const data = await res.json();
            if (data.running) {
                setDesktopActive(true);
                setClosedPanels(_reopenPanel('desktop'));
            } else {
                addToast(data.error || 'Desktop is not available', { type: 'error' });
            }
        } catch {
            addToast('Could not reach the server', { type: 'error' });
        }
    }, [desktopActive, closedPanels, addToast]);

    const newConversation = useCallback(async () => {
        await chatNewConversation();
        setBrowserSnapshot(null);
        setFilePreview(null);
        setTerminalLines([]);
        setGenerationPreview(null);
        setDesktopActive(false);
        setClosedPanels(new Set());
        setToolsPanelKey((k) => k + 1);
        agentDispatch({ type: 'RESET' });
    }, [chatNewConversation, agentDispatch]);

    // Determine view mode
    const agentState = useAgentState();
    const hasSubAgentNodes = hasSubAgents(agentState);
    const selectedAgent = agentState.selectedAgentId;

    // Preview panel visibility (for simple chat mode — no sub-agents)
    const showBrowser = browserSnapshot && !closedPanels.has('browser');
    const showDesktop = desktopActive && !closedPanels.has('desktop');
    const showTerminal = terminalLines.length > 0 && !closedPanels.has('terminal');
    const showGeneration = generationPreview && !closedPanels.has('generation');
    const hasAnyPanel = showBrowser || showDesktop || showTerminal || showGeneration;

    // View modes:
    // 1. selectedAgent → expanded agent activity view (no chat panel)
    // 2. hasSubAgentNodes → network overview + chat panel
    // 3. default → simple chat with preview panels (like today)

    return (
        <div className={styles.appShell}>
            {/* Slim header */}
            <Header
                dark={dark}
                onToggleTheme={onToggleTheme}
                onNewConversation={newConversation}
                audio={pendingAudio}
                muted={muted}
                onToggleMute={() => setMuted((m) => !m)}
                onAudioEnded={() => setPendingAudio(null)}
                onOpenDesktop={openDesktop}
            />

            <div className={styles.bodyRow}>
                {/* Icon sidebar */}
                <Sidebar
                    activePanel={flyoutPanel}
                    onPanelToggle={(panel) => {
                        if (panel === 'agents') {
                            // Agents icon returns to network overview
                            agentDispatch({ type: 'SELECT_AGENT', agentId: null });
                            setFlyoutPanel(null);
                        } else {
                            setFlyoutPanel(panel);
                        }
                    }}
                />

                {/* Flyout panel (settings, memory, etc.) — not for 'agents' which controls the main view */}
                {flyoutPanel && flyoutPanel !== 'agents' && (
                    <FlyoutPanel
                        title={flyoutPanel === 'settings' ? 'Model Settings'
                            : flyoutPanel === 'memory' ? 'Memory'
                            : flyoutPanel === 'conversations' ? 'Conversations'
                            : flyoutPanel === 'tools' ? 'Custom Tools'
                            : 'Panel'}
                        onClose={() => setFlyoutPanel(null)}
                    >
                        {flyoutPanel === 'settings' && (
                            <ModelSettingsPanel settings={modelSettings} disabled={isStreaming} />
                        )}
                        {flyoutPanel === 'memory' && (
                            <MemoryPanel refreshSignal={memoryRefreshSignal} />
                        )}
                        {flyoutPanel === 'conversations' && (
                            <ConversationsPanel onLoadConversation={loadConversation} />
                        )}
                        {flyoutPanel === 'tools' && (
                            <CustomToolsPanel key={toolsPanelKey} refreshSignal={toolsRefreshSignal} onToolsChanged={() => setToolsPanelKey(k => k + 1)} />
                        )}
                    </FlyoutPanel>
                )}

                {/* Main content area */}
                <div className={styles.mainContent}>
                    {selectedAgent ? (
                        /* Expanded agent activity view */
                        <AgentActivityView onNudge={(text) => handleSend(text, null, null)} />
                    ) : hasSubAgentNodes ? (
                        /* Network overview + chat */
                        <div className={styles.networkWithChat}>
                            <div className={styles.networkArea}>
                                <AgentNetwork />
                            </div>
                            <div className={styles.chatArea}>
                                <ChatPanel
                                    messages={messages}
                                    onSend={handleSend}
                                    onStop={stopGeneration}
                                    isStreaming={isStreaming}
                                    attachment={attachment}
                                    onPreview={(item) => setFilePreview(item)}
                                />
                            </div>
                        </div>
                    ) : (
                        /* Simple chat with preview panels */
                        <div className={`${styles.simpleChat} ${hasAnyPanel ? styles.withPanels : ''}`}>
                            {hasAnyPanel && (
                                <div className={styles.previewColumn}>
                                    {showGeneration && <GenerationPreview preview={generationPreview} onClose={() => setClosedPanels(_closePanel('generation'))} />}
                                    {showBrowser && <BrowserPreview snapshot={browserSnapshot} onAttachScreenshot={handleAttachScreenshot} onClose={() => setClosedPanels(_closePanel('browser'))} />}
                                    {showDesktop && <DesktopPreview visible={showDesktop} onClose={() => setClosedPanels(_closePanel('desktop'))} />}
                                    {showTerminal && <TerminalPanel lines={terminalLines} onClose={() => setClosedPanels(_closePanel('terminal'))} />}
                                </div>
                            )}
                            <div className={styles.chatColumn}>
                                <ChatPanel
                                    messages={messages}
                                    onSend={handleSend}
                                    onStop={stopGeneration}
                                    isStreaming={isStreaming}
                                    attachment={attachment}
                                    onPreview={(item) => {
                                        setFilePreview(item);
                                        setClosedPanels((prev) => {
                                            const next = new Set(prev);
                                            next.delete('file');
                                            next.add('generation');
                                            return next;
                                        });
                                    }}
                                />
                            </div>
                        </div>
                    )}
                </div>
            </div>

            {/* File preview overlay — available in all layouts */}
            {filePreview && (
                <FilePreview
                    item={filePreview}
                    onClose={() => {
                        setFilePreview(null);
                        setClosedPanels(_closePanel('file'));
                    }}
                />
            )}

            {nudgeToast && (
                <div className={styles.nudgeToast}>{nudgeToast}</div>
            )}
        </div>
    );
}

export default function DesktopApp(props) {
    return (
        <AgentStateProvider>
            <DesktopAppInner {...props} />
        </AgentStateProvider>
    );
}
