import { useState, useEffect, useRef, useCallback, useMemo } from 'react';

import Header from './components/Header.jsx';
import ChatPanel from './components/ChatPanel.jsx';
import BrowserPreview from './components/BrowserPreview.jsx';
import DesktopPreview from './components/DesktopPreview.jsx';
import CustomToolsPanel from './components/CustomToolsPanel.jsx';
import ConversationsPanel from './components/ConversationsPanel.jsx';
import MemoryPanel from './components/MemoryPanel.jsx';
import IntegrationsTab from './components/integrations/IntegrationsTab.jsx';
import SettingsPage from './components/SettingsPage.jsx';
import SystemSettings from './components/SystemSettings.jsx';
import ProfilesTab from './components/ProfilesTab.jsx';
import SetupWizard from './components/SetupWizard.jsx';
import useAgentProfiles from './hooks/useAgentProfiles.js';
import TerminalPanel from './components/TerminalOutput.jsx';
import GenerationPreview from './components/GenerationPreview.jsx';
import AgentNetwork from './components/AgentNetwork.jsx';
import AgentActivityView from './components/AgentActivityView.jsx';
import Sidebar from './components/Sidebar.jsx';
import FlyoutPanel from './components/FlyoutPanel.jsx';
import GoalsView from './components/goals/GoalsView.jsx';
import PreviewPanel from './components/PreviewPanel.jsx';
import SplitHandle from './components/SplitHandle.jsx';
import FilePreviewInline from './components/FilePreviewInline.jsx';
import FileFullscreen from './components/FileFullscreen.jsx';
import BrowserFullscreen from './components/BrowserFullscreen.jsx';
import useFeatures from './hooks/useFeatures.js';
import useGoals from './hooks/useGoals.js';
// useModelSettings removed — replaced by profile-based configuration
import useStreamingChat from './hooks/useStreamingChat.js';
import usePreviewState from './hooks/usePreviewState.jsx';
import { AgentStateProvider, useAgentState, useAgentDispatch } from './hooks/useAgentState.jsx';
import { useToast } from './components/ToastProvider.jsx';
import styles from './App.module.css';

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
    const [attachment, setAttachment] = useState(null);
    const [flyoutPanel, setFlyoutPanel] = useState(null);
    const [toolsPanelKey, setToolsPanelKey] = useState(0);
    const [memoryRefreshSignal, setMemoryRefreshSignal] = useState(0);
    const [toolsRefreshSignal, setToolsRefreshSignal] = useState(0);
    const [pendingAudio, setPendingAudio] = useState(null);
    const [muted, setMuted] = useState(false);
    const [userDesktopOpen, setUserDesktopOpen] = useState(false);
    const [networkViewOpen, setNetworkViewOpen] = useState(false);
    const features = useFeatures();
    const [selectedProfileId, setSelectedProfileId] = useState(() => {
        return localStorage.getItem('computron_profile_id') || 'computron';
    });
    const handleProfileChange = useCallback((id) => {
        setSelectedProfileId(id);
        localStorage.setItem('computron_profile_id', id);
    }, []);

    // Setup wizard state
    const [setupComplete, setSetupComplete] = useState(null); // null = loading
    const wasSetupComplete = useRef(false);
    const [settingsTab, setSettingsTab] = useState('profiles');

    useEffect(() => {
        fetch('/api/settings').then(r => r.json()).then(data => {
            const done = data.setup_complete || false;
            wasSetupComplete.current = done;
            setSetupComplete(done);
        }).catch(() => setSetupComplete(false));
    }, []);

    // Agent profiles for the settings page builder
    const profilesHook = useAgentProfiles();

    const goalsState = useGoals(flyoutPanel === 'goals');
    const goalsActive = flyoutPanel === 'goals';
    const { addToast } = useToast();

    const preview = usePreviewState(agentState, agentDispatch);

    // ── Stream callbacks ──────────────────────────────────────────────
    // Called by useStreamingChat when events arrive from the backend.
    // Preview events dispatch once to the agent reducer — no dual state.
    //
    // Created once via useRef — the streaming hook keeps a stable reference
    // and doesn't restart on re-render. All callbacks use dispatch/setState
    // updaters which are stable across renders. Do NOT read state variables
    // directly in these callbacks — they would capture a stale closure.
    const _callbacks = useRef({
        onBrowserSnapshot: (snapshot) => {
            agentDispatch({ type: 'UPDATE_BROWSER_SNAPSHOT', agentId: snapshot.agentId, snapshot });
        },
        onTerminalOutput: (event) => {
            agentDispatch({ type: 'UPDATE_TERMINAL', agentId: event.agentId, event });
        },
        onToolCreated: () => setToolsRefreshSignal((s) => s + 1),
        onMemoryChanged: () => setMemoryRefreshSignal((s) => s + 1),
        onAudioPlayback: (audio) => setPendingAudio(audio),
        onNudgeSent: (result) => {
            if (result.ok) {
                addToast('Nudge sent', { type: 'info', duration: 3000 });
            } else if (result.status === 409) {
                addToast('Agent is no longer running', { type: 'warn', duration: 5000 });
            } else {
                addToast(result.error || 'Could not send nudge', { type: 'error' });
            }
        },
        onDesktopActive: (agentId) => {
            agentDispatch({ type: 'UPDATE_DESKTOP_ACTIVE', agentId });
        },
        onGenerationPreview: (event) => {
            agentDispatch({ type: 'UPDATE_GENERATION_PREVIEW', agentId: event.agentId, preview: event });
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
        // When an agent uses a tool, update the card badge. Activity log
        // entries are buffered by useStreamingChat for correct ordering.
        onAgentToolCall: ({ name, agentId }) => {
            agentDispatch({ type: 'UPDATE_ACTIVE_TOOL', agentId, toolName: name });
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
        // Agent file output — activity log entry is buffered by
        // useStreamingChat, this callback handles any side effects.
        onAgentFileOutput: () => {},
        // Buffered activity log entry (tool call, file output) — dispatched
        // by useStreamingChat in correct chronological order.
        onActivityEntry: ({ agentId, entry }) => {
            agentDispatch({ type: 'APPEND_ACTIVITY', agentId, entry });
        },
    }).current;

    const {
        messages,
        isStreaming,
        sendMessage,
        sendNudge,
        stopGeneration,
        loadConversation,
        newConversation: chatNewConversation,
    } = useStreamingChat(_callbacks);

    const handleSend = useCallback((message, fileData) => {
        setAttachment(null);
        if (isStreaming) {
            sendNudge(message);
        } else {
            sendMessage(message, fileData, selectedProfileId);
        }
    }, [sendMessage, sendNudge, isStreaming, selectedProfileId]);

    const openDesktop = useCallback(async () => {
        if (userDesktopOpen) return;
        try {
            const res = await fetch('/api/desktop/start', { method: 'POST' });
            const data = await res.json();
            if (data.running) {
                setUserDesktopOpen(true);
            } else {
                addToast(data.error || 'Desktop is not available', { type: 'error' });
            }
        } catch {
            addToast('Could not reach the server', { type: 'error' });
        }
    }, [userDesktopOpen, addToast]);

    const newConversation = useCallback(async () => {
        await chatNewConversation();
        preview.reset();
        setNetworkViewOpen(false);
        setToolsPanelKey((k) => k + 1);
        agentDispatch({ type: 'RESET' });
    }, [chatNewConversation, preview.reset, agentDispatch]);

    // ── Which layout to show ───────────────────────────────────────────
    // Two top-level views:
    //
    //   1. Simple chat (default) — chat + preview panels. Always shows the
    //      root agent's conversation. When sub-agents have been spawned, a
    //      network indicator appears so the user can navigate to the network.
    //
    //   2. Network view — full-screen agent graph. Click a card to drill
    //      into an agent's activity view. Close to return to simple chat.
    //
    // Flow: simple chat ⇄ network view (via indicator/sidebar)
    //       network → agent detail (click card) → back to network ("← Agents")

    // Compute network-visible agent stats for the indicator badge.
    // Counts all agents in trees that have sub-agents (same as the
    // network view header) so the numbers match when you open it.
    const { networkAgentCount, networkRunningCount } = useMemo(() => {
        const agents = agentState.agents;
        let total = 0, running = 0;
        // Walk each root that has children (same filter as _buildTrees)
        for (const a of Object.values(agents)) {
            if (a.parentId !== null || a.childIds.length === 0) continue;
            // BFS this tree
            const queue = [a.id];
            while (queue.length > 0) {
                const id = queue.shift();
                const node = agents[id];
                if (!node) continue;
                total++;
                if (node.status === 'running') running++;
                for (const childId of node.childIds) queue.push(childId);
            }
        }
        return { networkAgentCount: total, networkRunningCount: running };
    }, [agentState.agents]);

    const handleOpenNetwork = useCallback(() => {
        setNetworkViewOpen(true);
        setFlyoutPanel(null);
    }, []);

    const handleCloseNetwork = useCallback(() => {
        setNetworkViewOpen(false);
        agentDispatch({ type: 'SELECT_AGENT', agentId: null });
    }, [agentDispatch]);

    const hasPreview = preview.tabs.length > 0 && !goalsActive && flyoutPanel !== 'settings' && (!networkViewOpen || !!agentState.selectedAgentId);

    // Show setup wizard if setup is not complete
    if (setupComplete === false) {
        return (
            <SetupWizard isRerun={wasSetupComplete.current} onComplete={() => {
                setSetupComplete(true);
                profilesHook.refresh();
            }} />
        );
    }

    // Still loading setup status
    if (setupComplete === null) {
        return null;
    }

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
                desktopEnabled={features.desktop}
                onOpenDesktop={openDesktop}
            />

            <div className={styles.bodyRow}>
                {/* Icon sidebar */}
                <Sidebar
                    hiddenPanels={features.custom_tools ? [] : ['tools']}
                    activePanel={networkViewOpen ? 'agents' : flyoutPanel}
                    onPanelToggle={(panel) => {
                        if (panel === 'agents') {
                            // Toggle the network view open/closed
                            if (networkViewOpen) {
                                handleCloseNetwork();
                            } else if (agentState.networkActivated) {
                                handleOpenNetwork();
                            }
                            goalsState.setSelectedGoalId(null);
                        } else {
                            // Close network view when opening a flyout panel
                            if (networkViewOpen) handleCloseNetwork();
                            setFlyoutPanel(panel);
                        }
                    }}
                />

                {/* Flyout panel (settings, memory, goals, etc.) — not for 'agents' which controls the main view */}
                {flyoutPanel && flyoutPanel !== 'agents' && flyoutPanel !== 'goals' && flyoutPanel !== 'settings' && (
                    <FlyoutPanel
                        title={flyoutPanel === 'memory' ? 'Memory'
                            : flyoutPanel === 'conversations' ? 'Conversations'
                            : flyoutPanel === 'tools' ? 'Custom Tools'
                            : 'Panel'}
                        onClose={() => setFlyoutPanel(null)}
                    >
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
                    {/* Settings page — full view when settings icon clicked */}
                    {flyoutPanel === 'settings' && (
                        <SettingsPage activeTab={settingsTab} onTabChange={setSettingsTab}>
                            {settingsTab === 'profiles' && (
                                <ProfilesTab profilesHook={profilesHook} features={features} />
                            )}
                            {settingsTab === 'integrations' && (
                                <IntegrationsTab />
                            )}
                            {settingsTab === 'system' && (
                                <SystemSettings />
                            )}
                        </SettingsPage>
                    )}

                    {/* Goals split-screen view */}
                    {goalsActive && (
                        <GoalsView
                            goals={goalsState.goals}
                            runnerStatus={goalsState.runnerStatus}
                            selectedGoalId={goalsState.selectedGoalId}
                            setSelectedGoalId={goalsState.setSelectedGoalId}
                            deleteGoal={goalsState.deleteGoal}
                            deleteRun={goalsState.deleteRun}
                            pauseGoal={goalsState.pauseGoal}
                            resumeGoal={goalsState.resumeGoal}
                            triggerGoal={goalsState.triggerGoal}
                            fetchDetail={goalsState.fetchGoalDetail}
                        />
                    )}
                    {!goalsActive && flyoutPanel !== 'settings' && networkViewOpen && !agentState.selectedAgentId && (
                        <div className={styles.networkArea}>
                            <AgentNetwork onClose={handleCloseNetwork} agentCount={networkAgentCount} />
                        </div>
                    )}

                    {/* Agent activity — left column when drilling into an agent */}
                    {!goalsActive && flyoutPanel !== 'settings' && networkViewOpen && agentState.selectedAgentId && (
                        <div className={styles.chatColumn}
                             style={{ width: hasPreview ? `${preview.splitPosition}%` : '100%' }}>
                            <AgentActivityView onNudge={sendNudge} onPreview={preview.openFile} />
                        </div>
                    )}

                    {/* Chat — always mounted, hidden when goals/network/settings active */}
                    <div className={`${styles.chatColumn} ${networkViewOpen || goalsActive || flyoutPanel === 'settings' ? styles.hidden : ''}`}
                         style={{ width: hasPreview && !networkViewOpen && !goalsActive && flyoutPanel !== 'settings' ? `${preview.splitPosition}%` : '100%' }}>
                        <ChatPanel
                            messages={messages}
                            onSend={handleSend}
                            onStop={stopGeneration}
                            isStreaming={isStreaming}
                            attachment={attachment}
                            rootAgent={preview.rootAgent}
                            networkActivated={agentState.networkActivated}
                            networkAgentCount={networkAgentCount}
                            networkRunningCount={networkRunningCount}
                            onOpenNetwork={handleOpenNetwork}
                            selectedProfileId={selectedProfileId}
                            onProfileChange={handleProfileChange}
                            profileRefreshSignal={profilesHook.revision}
                            onPreview={preview.openFile}
                        />
                    </div>

                    {/* Shared split handle + preview panel — visible alongside chat OR agent activity */}
                    {hasPreview && (
                        <>
                            <SplitHandle onDrag={preview.setSplitPosition} />
                            <div className={styles.previewColumn}>
                                <PreviewPanel
                                    tabs={preview.tabs}
                                    activeTab={preview.activeTab}
                                    onTabChange={preview.setActiveTab}
                                    onCloseTab={preview.closeTab}
                                >
                                    {preview.activeTab === 'browser' && preview.browserSnapshot && (
                                        <BrowserPreview
                                            snapshot={preview.browserSnapshot}
                                            onFullscreen={() => preview.setFullscreenItem({ kind: 'browser' })}
                                        />
                                    )}
                                    {preview.activeTab?.startsWith('file:') && (() => {
                                        const filename = preview.activeTab.slice(5);
                                        const file = preview.openFiles.find(f => f.filename === filename);
                                        return file ? (
                                            <FilePreviewInline
                                                item={file}
                                                onFullscreen={() => preview.setFullscreenItem({ kind: 'file', file })}
                                            />
                                        ) : null;
                                    })()}
                                    {preview.activeTab === 'terminal' && preview.terminalLines.length > 0 && (
                                        <TerminalPanel lines={preview.terminalLines} />
                                    )}
                                    {preview.activeTab === 'desktop' && preview.desktopActive && (
                                        <DesktopPreview visible />
                                    )}
                                    {preview.activeTab === 'generation' && preview.generationPreview && (
                                        <GenerationPreview preview={preview.generationPreview} />
                                    )}
                                </PreviewPanel>
                            </div>
                        </>
                    )}
                </div>
            </div>

            {/* User's personal desktop overlay — opened via the header button,
                independent of any agent's desktop. Floats on top of all views. */}
            {userDesktopOpen && (
                <DesktopPreview visible={true} onClose={() => setUserDesktopOpen(false)} overlay />
            )}

            {/* Fullscreen preview — fills entire viewport */}
            {preview.fullscreenItem?.kind === 'file' && (
                <FileFullscreen
                    item={preview.fullscreenItem.file}
                    onClose={() => preview.setFullscreenItem(null)}
                />
            )}
            {preview.fullscreenItem?.kind === 'browser' && preview.browserSnapshot && (
                <BrowserFullscreen
                    snapshot={preview.browserSnapshot}
                    onClose={() => preview.setFullscreenItem(null)}
                />
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
