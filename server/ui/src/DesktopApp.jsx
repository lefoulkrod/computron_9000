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
import { AgentStateProvider, useAgentState, useAgentDispatch, hasSubAgents } from './hooks/useAgentState.jsx';
import { useToast } from './components/ToastProvider.jsx';
import styles from './App.module.css';

// Track which preview panels the user has closed (by name).
// _reopenPanel shows it again, _closePanel hides it.
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

/**
 * Main app shell. Preview data (browser screenshots, terminal output, etc.)
 * lives in the agent reducer — one source of truth for all views. The
 * simple chat preview column reads from the root agent's node, same as
 * the agent detail view reads from any selected agent's node.
 */
function DesktopAppInner({ dark, onToggleTheme }) {
    const agentDispatch = useAgentDispatch();
    const agentState = useAgentState();

    // ── UI-only state (not duplicated in the reducer) ───────────────
    const [filePreview, setFilePreview] = useState(null);
    const [attachment, setAttachment] = useState(null);
    const [flyoutPanel, setFlyoutPanel] = useState(null);
    const [toolsPanelKey, setToolsPanelKey] = useState(0);
    const [memoryRefreshSignal, setMemoryRefreshSignal] = useState(0);
    const [toolsRefreshSignal, setToolsRefreshSignal] = useState(0);
    const [pendingAudio, setPendingAudio] = useState(null);
    const [muted, setMuted] = useState(false);
    const [closedPanels, setClosedPanels] = useState(new Set());
    const [nudgeToast, setNudgeToast] = useState(null);

    const modelSettings = useModelSettings();
    const { addToast } = useToast();

    // ── Read preview data from root agent in the reducer ────────────
    const rootAgent = agentState.rootId ? agentState.agents[agentState.rootId] : null;
    const browserSnapshot = rootAgent?.browserSnapshot || null;
    const terminalLines = rootAgent?.terminalLines || [];
    const desktopActive = rootAgent?.desktopActive || false;
    const generationPreview = rootAgent?.generationPreview || null;

    // ── Stream callbacks ──────────────────────────────────────────────
    // Called by useStreamingChat when events arrive from the backend.
    // Preview events dispatch once to the agent reducer — no dual state.
    //
    // We use a ref so the streaming hook keeps a stable reference and
    // doesn't restart the connection on re-render. The closedPanels
    // updates need fresh state, so we read via the ref on each call.
    const _callbacks = useRef({
        onBrowserSnapshot: (snapshot) => {
            agentDispatch({ type: 'UPDATE_BROWSER_SNAPSHOT', agentId: snapshot.agentId, snapshot });
            setClosedPanels(_reopenPanel('browser'));
        },
        onTerminalOutput: (event) => {
            agentDispatch({ type: 'UPDATE_TERMINAL', agentId: event.agentId, event });
            setClosedPanels(_reopenPanel('terminal'));
        },
        onToolCreated: () => setToolsRefreshSignal((s) => s + 1),
        onMemoryChanged: () => setMemoryRefreshSignal((s) => s + 1),
        onAudioPlayback: (audio) => setPendingAudio(audio),
        onNudgeSent: (text) => setNudgeToast(text || 'Nudge sent'),
        onDesktopActive: (agentId) => {
            agentDispatch({ type: 'UPDATE_DESKTOP_ACTIVE', agentId });
            setClosedPanels(_reopenPanel('desktop'));
        },
        onGenerationPreview: (event) => {
            agentDispatch({ type: 'UPDATE_GENERATION_PREVIEW', agentId: event.agentId, preview: event });
            // Show generation panel, hide file panel (they share the same slot)
            setClosedPanels((prev) => {
                if (!prev.has('generation') && prev.has('file')) return prev;
                const next = new Set(prev);
                next.delete('generation');
                next.add('file');
                return next;
            });
        },
        // When an agent starts or finishes, add/update it in the tree.
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
        // When an agent uses a tool, show it on the card and log it.
        onAgentToolCall: ({ name, agentId }) => {
            agentDispatch({ type: 'UPDATE_ACTIVE_TOOL', agentId, toolName: name });
            agentDispatch({
                type: 'APPEND_ACTIVITY',
                agentId,
                entry: { type: 'tool_call', name, timestamp: Date.now() },
            });
        },
        // Sub-agent text tokens, batched ~60x/sec. We merge content and
        // thinking in one update so they don't get jumbled together.
        onAgentContent: ({ agentId, content, thinking }) => {
            agentDispatch({
                type: 'APPEND_STREAM_CHUNK',
                agentId,
                content: content || null,
                thinking: thinking || null,
            });
        },
        // Agent context usage (iteration + context window fill)
        onAgentContextUsage: ({ agentId, iteration, maxIterations, contextUsage }) => {
            agentDispatch({ type: 'UPDATE_ITERATION', agentId, iteration, maxIterations, contextUsage });
        },
        // Agent file output
        onAgentFileOutput: ({ agentId, ...fileEvent }) => {
            agentDispatch({
                type: 'APPEND_ACTIVITY',
                agentId,
                entry: { type: 'file_output', ...fileEvent, timestamp: Date.now() },
            });
        },
    }).current;

    const {
        messages,
        isStreaming,
        sendMessage,
        stopGeneration,
        loadConversation,
        newConversation: chatNewConversation,
    } = useStreamingChat(_callbacks);

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
                // Desktop started outside an agent span — dispatch directly
                // to the root agent node so the preview panel appears.
                if (agentState.rootId) {
                    agentDispatch({ type: 'UPDATE_DESKTOP_ACTIVE', agentId: agentState.rootId });
                }
                setClosedPanels(_reopenPanel('desktop'));
            } else {
                addToast(data.error || 'Desktop is not available', { type: 'error' });
            }
        } catch {
            addToast('Could not reach the server', { type: 'error' });
        }
    }, [desktopActive, closedPanels, addToast, agentState.rootId, agentDispatch]);

    const newConversation = useCallback(async () => {
        await chatNewConversation();
        setFilePreview(null);
        setClosedPanels(new Set());
        setToolsPanelKey((k) => k + 1);
        agentDispatch({ type: 'RESET' });
    }, [chatNewConversation, agentDispatch]);

    // ── Which layout to show ───────────────────────────────────────────
    // Three possible views:
    //
    //   1. Agent detail — user clicked a card → full-screen activity view
    //   2. Agent network — sub-agents exist → tree graph + chat side by side
    //   3. Simple chat — no sub-agents → classic chat + preview panels
    //
    // Flow: simple chat → network (when first sub-agent spawns)
    //       → detail (click a card) → back to network ("← Agents" button)
    const hasSubAgentNodes = hasSubAgents(agentState);
    const selectedAgent = agentState.selectedAgentId;

    // Which preview panels are visible (simple chat + desktop overlay)
    const showBrowser = browserSnapshot && !closedPanels.has('browser');
    const showDesktop = desktopActive && !closedPanels.has('desktop');
    const showTerminal = terminalLines.length > 0 && !closedPanels.has('terminal');
    const showGeneration = generationPreview && !closedPanels.has('generation');
    const hasAnyPanel = showBrowser || showDesktop || showTerminal || showGeneration;

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
                        <AgentActivityView onNudge={(text) => handleSend(text, null, null)} onPreview={(item) => setFilePreview(item)} />
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
                        /* Simple chat with preview panels — reads from root agent */
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

            {/* Desktop overlay — in agent views there's no preview column,
                so the desktop floats on top instead */}
            {showDesktop && (hasSubAgentNodes || selectedAgent) && (
                <DesktopPreview visible={true} onClose={() => setClosedPanels(_closePanel('desktop'))} overlay />
            )}

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

/** Wraps the app in the agent state provider so all children can read/update agent data. */
export default function DesktopApp(props) {
    return (
        <AgentStateProvider>
            <DesktopAppInner {...props} />
        </AgentStateProvider>
    );
}
