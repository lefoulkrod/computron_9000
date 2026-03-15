import { useState, useEffect, useRef, useCallback } from 'react';

import Header from './components/Header.jsx';
import ChatInput from './components/ChatInput.jsx';
import ChatMessages from './components/ChatMessages.jsx';
import BrowserView from './components/BrowserView.jsx';
import FilePreviewPanel from './components/FilePreviewPanel.jsx';
import CustomToolsPanel from './components/CustomToolsPanel.jsx';
import SkillsPanel from './components/SkillsPanel.jsx';
import SessionsPanel from './components/SessionsPanel.jsx';
import MemoryPanel from './components/MemoryPanel.jsx';
import ModelSettingsPanel from './components/ModelSettingsPanel.jsx';
import TerminalPanel from './components/TerminalOutput.jsx';
import GenerationPreview from './components/GenerationPreview.jsx';
import useModelSettings from './hooks/useModelSettings.js';
import useStreamingChat from './hooks/useStreamingChat.js';
import styles from './App.module.css';

function App() {
    const [dark, setDark] = useState(false);
    const [browserSnapshot, setBrowserSnapshot] = useState(null);
    const [filePreview, setFilePreview] = useState(null);
    const [attachment, setAttachment] = useState(null);
    const [showSubAgents, setShowSubAgents] = useState(true);
    const [toolsPanelKey, setToolsPanelKey] = useState(0);
    const [memoryRefreshSignal, setMemoryRefreshSignal] = useState(0);
    const [toolsRefreshSignal, setToolsRefreshSignal] = useState(0);
    const [pendingAudio, setPendingAudio] = useState(null);
    const [muted, setMuted] = useState(false);
    const [terminalLines, setTerminalLines] = useState([]);
    const [generationPreview, setGenerationPreview] = useState(null);
    const [skillsRefreshSignal, setSkillsRefreshSignal] = useState(0);
    const [activeSkill, setActiveSkill] = useState(null);
    // Tracks panels the user has explicitly closed; new events reopen them.
    const [closedPanels, setClosedPanels] = useState(new Set());
    const [nudgeToast, setNudgeToast] = useState(null);

    const modelSettings = useModelSettings();

    // Stable callbacks ref for streaming chat side effects.
    // The ref is reassigned every render so it always has fresh setters,
    // but the delegating object identity never changes.
    const _streamCallbacksRef = useRef(null);
    _streamCallbacksRef.current = {
        onBrowserSnapshot: (snapshot) => {
            setBrowserSnapshot(snapshot);
            setClosedPanels((prev) => prev.has('browser') ? (() => { const next = new Set(prev); next.delete('browser'); return next; })() : prev);
        },
        onTerminalOutput: (event) => {
            setTerminalLines((prev) => {
                const idx = prev.findIndex((e) => e.cmd_id === event.cmd_id);
                if (idx !== -1) {
                    const updated = [...prev];
                    if (event.status === 'streaming') {
                        const existing = updated[idx];
                        updated[idx] = {
                            ...existing,
                            status: 'streaming',
                            stdout: (existing.stdout || '') + (event.stdout || '') || null,
                            stderr: (existing.stderr || '') + (event.stderr || '') || null,
                        };
                    } else {
                        updated[idx] = event;
                    }
                    return updated;
                }
                return [...prev, event];
            });
            setClosedPanels((prev) => prev.has('terminal') ? (() => { const next = new Set(prev); next.delete('terminal'); return next; })() : prev);
        },
        onToolCreated: () => setToolsRefreshSignal((s) => s + 1),
        onMemoryChanged: () => setMemoryRefreshSignal((s) => s + 1),
        onAudioPlayback: (audio) => setPendingAudio(audio),
        onNudgeSent: (text) => setNudgeToast(text || 'Nudge sent'),
        onSkillApplied: (event) => {
            setActiveSkill(event);
            setSkillsRefreshSignal((s) => s + 1);
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
        },
    };
    const _stableCallbacks = useRef({
        onBrowserSnapshot: (...args) => _streamCallbacksRef.current.onBrowserSnapshot(...args),
        onTerminalOutput: (...args) => _streamCallbacksRef.current.onTerminalOutput(...args),
        onToolCreated: (...args) => _streamCallbacksRef.current.onToolCreated(...args),
        onMemoryChanged: (...args) => _streamCallbacksRef.current.onMemoryChanged(...args),
        onAudioPlayback: (...args) => _streamCallbacksRef.current.onAudioPlayback(...args),
        onNudgeSent: (...args) => _streamCallbacksRef.current.onNudgeSent(...args),
        onSkillApplied: (...args) => _streamCallbacksRef.current.onSkillApplied(...args),
        onGenerationPreview: (...args) => _streamCallbacksRef.current.onGenerationPreview(...args),
    }).current;

    const {
        messages,
        isStreaming,
        sendMessage,
        stopGeneration,
        loadSession,
        newSession: chatNewSession,
    } = useStreamingChat(_stableCallbacks);

    // Clear active skill indicator when streaming ends
    useEffect(() => {
        if (!isStreaming) setActiveSkill(null);
    }, [isStreaming]);

    // Auto-dismiss nudge toast after 3 seconds
    useEffect(() => {
        if (!nudgeToast) return;
        const timer = setTimeout(() => setNudgeToast(null), 3000);
        return () => clearTimeout(timer);
    }, [nudgeToast]);

    useEffect(() => {
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        setDark(prefersDark);
    }, []);

    useEffect(() => {
        document.body.classList.toggle('dark-theme', dark);
    }, [dark]);

    const toggleTheme = () => setDark((d) => !d);
    const toggleSubAgents = () => setShowSubAgents((s) => !s);

    const handleAttachScreenshot = (base64Screenshot) => {
        setAttachment({ base64: base64Screenshot, contentType: 'image/png' });
    };

    // Wrap sendMessage to pass model settings, agent selection, and clear attachment
    const handleSend = useCallback((message, fileData, agent) => {
        setAttachment(null);
        sendMessage(message, fileData, {
            selectedModel: modelSettings.selectedModel,
            contextKb: modelSettings.contextKb,
            think: modelSettings.think,
            persistThinking: modelSettings.persistThinking,
            temperature: modelSettings.temperature,
            topK: modelSettings.topK,
            topP: modelSettings.topP,
            repeatPenalty: modelSettings.repeatPenalty,
            numPredict: modelSettings.numPredict,
            unlimitedTurns: modelSettings.unlimitedTurns,
            agentTurns: modelSettings.agentTurns,
        }, agent);
    }, [sendMessage, modelSettings.selectedModel, modelSettings.contextKb,
        modelSettings.think, modelSettings.persistThinking, modelSettings.temperature, modelSettings.topK,
        modelSettings.topP, modelSettings.repeatPenalty, modelSettings.numPredict,
        modelSettings.unlimitedTurns, modelSettings.agentTurns]);

    // New session: reset chat + panel state
    const newSession = useCallback(async () => {
        await chatNewSession();
        setBrowserSnapshot(null);
        setFilePreview(null);
        setTerminalLines([]);
        setGenerationPreview(null);
        setClosedPanels(new Set());
        setToolsPanelKey((k) => k + 1);
    }, [chatNewSession]);

    // Each panel shows if it has data and the user hasn't closed it
    const showGeneration = generationPreview && !closedPanels.has('generation');
    const showFile = filePreview && !closedPanels.has('file');
    const showBrowser = browserSnapshot && !closedPanels.has('browser');
    const showTerminal = terminalLines.length > 0 && !closedPanels.has('terminal');
    const hasAnyPanel = showGeneration || showFile || showBrowser || showTerminal;

    return (
        <>
            <Header
                dark={dark}
                onToggleTheme={toggleTheme}
                onNewSession={newSession}
                showSubAgents={showSubAgents}
                onToggleSubAgents={toggleSubAgents}
                audio={pendingAudio}
                muted={muted}
                onToggleMute={() => setMuted((m) => !m)}
                onAudioEnded={() => setPendingAudio(null)}
            />
            <div className={`${styles.mainLayout} ${hasAnyPanel ? styles.threeColumn : ''}`}>
                <div className={styles.column}>
                    <div className={styles.stickyInput}>
                        <ChatInput
                            onSend={handleSend}
                            onStop={stopGeneration}
                            isStreaming={isStreaming}
                            attachment={attachment}
                        />
                    </div>
                    <ModelSettingsPanel
                        models={modelSettings.availableModels}
                        selectedModel={modelSettings.selectedModel}
                        onModelChange={modelSettings.setSelectedModel}
                        contextKb={modelSettings.contextKb}
                        onContextKbChange={modelSettings.setContextKb}
                        think={modelSettings.think}
                        onThinkChange={modelSettings.setThink}
                        persistThinking={modelSettings.persistThinking}
                        onPersistThinkingChange={modelSettings.setPersistThinking}
                        temperature={modelSettings.temperature}
                        onTemperatureChange={modelSettings.setTemperature}
                        topK={modelSettings.topK}
                        onTopKChange={modelSettings.setTopK}
                        topP={modelSettings.topP}
                        onTopPChange={modelSettings.setTopP}
                        repeatPenalty={modelSettings.repeatPenalty}
                        onRepeatPenaltyChange={modelSettings.setRepeatPenalty}
                        numPredict={modelSettings.numPredict}
                        onNumPredictChange={modelSettings.setNumPredict}
                        unlimitedTurns={modelSettings.unlimitedTurns}
                        onUnlimitedTurnsChange={modelSettings.setUnlimitedTurns}
                        agentTurns={modelSettings.agentTurns}
                        onAgentTurnsChange={modelSettings.setAgentTurns}
                        disabled={isStreaming}
                    />
                    <MemoryPanel refreshSignal={memoryRefreshSignal} />
                    <CustomToolsPanel key={toolsPanelKey} refreshSignal={toolsRefreshSignal} onToolsChanged={() => setToolsPanelKey(k => k + 1)} />
                    <SkillsPanel refreshSignal={skillsRefreshSignal} />
                    <SessionsPanel onLoadSession={loadSession} />
                </div>
                {hasAnyPanel && (
                    <div className={styles.browserColumn}>
                        {/* Precedence: previews first, then browser, terminal always last */}
                        {showGeneration && (
                            <GenerationPreview preview={generationPreview} onClose={() => setClosedPanels((prev) => new Set(prev).add('generation'))} />
                        )}
                        {showFile && (
                            <FilePreviewPanel item={filePreview} onClose={() => setClosedPanels((prev) => new Set(prev).add('file'))} />
                        )}
                        {showBrowser && (
                            <BrowserView snapshot={browserSnapshot} onAttachScreenshot={handleAttachScreenshot} onClose={() => setClosedPanels((prev) => new Set(prev).add('browser'))} />
                        )}
                        {showTerminal && (
                            <TerminalPanel lines={terminalLines} onClose={() => setClosedPanels((prev) => new Set(prev).add('terminal'))} />
                        )}
                    </div>
                )}
                <div className={styles.column}>
                    <ChatMessages
                        messages={messages}
                        showSubAgents={showSubAgents}
                        activeSkill={activeSkill}
                        isStreaming={isStreaming}
                        onPreview={(item) => {
                            setFilePreview(item);
                            setClosedPanels((prev) => { const next = new Set(prev); next.delete('file'); next.add('generation'); return next; });
                        }}
                    />
                </div>
            </div>
            {nudgeToast && (
                <div className={styles.nudgeToast}>{nudgeToast}</div>
            )}
        </>
    );
}

export default App;
