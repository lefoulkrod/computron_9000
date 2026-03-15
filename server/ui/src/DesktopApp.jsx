import { useState, useEffect, useRef, useCallback } from 'react';

import Header from './components/Header.jsx';
import ChatInput from './components/ChatInput.jsx';
import ChatMessages from './components/ChatMessages.jsx';
import BrowserPreview from './components/BrowserPreview.jsx';
import DesktopPreview from './components/DesktopPreview.jsx';
import FilePreview from './components/FilePreview.jsx';
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

export default function DesktopApp({ dark, onToggleTheme }) {
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
    const [desktopActive, setDesktopActive] = useState(false);
    const [skillsRefreshSignal, setSkillsRefreshSignal] = useState(0);
    const [activeSkill, setActiveSkill] = useState(null);
    const [closedPanels, setClosedPanels] = useState(new Set());
    const [nudgeToast, setNudgeToast] = useState(null);

    const modelSettings = useModelSettings();

    const _streamCallbacksRef = useRef(null);
    _streamCallbacksRef.current = {
        onBrowserSnapshot: (snapshot) => {
            setBrowserSnapshot(snapshot);
            setClosedPanels(_reopenPanel('browser'));
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
            setClosedPanels(_reopenPanel('terminal'));
        },
        onToolCreated: () => setToolsRefreshSignal((s) => s + 1),
        onMemoryChanged: () => setMemoryRefreshSignal((s) => s + 1),
        onAudioPlayback: (audio) => setPendingAudio(audio),
        onNudgeSent: (text) => setNudgeToast(text || 'Nudge sent'),
        onSkillApplied: (event) => {
            setActiveSkill(event);
            setSkillsRefreshSignal((s) => s + 1);
        },
        onDesktopActive: () => {
            setDesktopActive(true);
            setClosedPanels(_reopenPanel('desktop'));
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
        onDesktopActive: (...args) => _streamCallbacksRef.current.onDesktopActive(...args),
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

    useEffect(() => {
        if (!isStreaming) setActiveSkill(null);
    }, [isStreaming]);

    useEffect(() => {
        if (!nudgeToast) return;
        const timer = setTimeout(() => setNudgeToast(null), 3000);
        return () => clearTimeout(timer);
    }, [nudgeToast]);

    const toggleSubAgents = () => setShowSubAgents((s) => !s);

    const handleAttachScreenshot = (base64Screenshot) => {
        setAttachment({ base64: base64Screenshot, contentType: 'image/png' });
    };

    const handleSend = useCallback((message, fileData, agent) => {
        setAttachment(null);
        sendMessage(message, fileData, modelSettings, agent);
    }, [sendMessage, modelSettings]);

    const newSession = useCallback(async () => {
        await chatNewSession();
        setBrowserSnapshot(null);
        setFilePreview(null);
        setTerminalLines([]);
        setGenerationPreview(null);
        setDesktopActive(false);
        setClosedPanels(new Set());
        setToolsPanelKey((k) => k + 1);
    }, [chatNewSession]);

    const showGeneration = generationPreview && !closedPanels.has('generation');
    const showFile = filePreview && !closedPanels.has('file');
    const showBrowser = browserSnapshot && !closedPanels.has('browser');
    const showDesktop = desktopActive && !closedPanels.has('desktop');
    const showTerminal = terminalLines.length > 0 && !closedPanels.has('terminal');
    const hasAnyPanel = showGeneration || showFile || showBrowser || showDesktop || showTerminal;

    return (
        <>
            <Header
                dark={dark}
                onToggleTheme={onToggleTheme}
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
                    <ModelSettingsPanel settings={modelSettings} disabled={isStreaming} />
                    <MemoryPanel refreshSignal={memoryRefreshSignal} />
                    <CustomToolsPanel key={toolsPanelKey} refreshSignal={toolsRefreshSignal} onToolsChanged={() => setToolsPanelKey(k => k + 1)} />
                    <SkillsPanel refreshSignal={skillsRefreshSignal} />
                    <SessionsPanel onLoadSession={loadSession} />
                </div>
                {hasAnyPanel && (
                    <div className={styles.browserColumn}>
                        {showGeneration && (
                            <GenerationPreview preview={generationPreview} onClose={() => setClosedPanels(_closePanel('generation'))} />
                        )}
                        {showFile && (
                            <FilePreview item={filePreview} onClose={() => setClosedPanels(_closePanel('file'))} />
                        )}
                        {showBrowser && (
                            <BrowserPreview snapshot={browserSnapshot} onAttachScreenshot={handleAttachScreenshot} onClose={() => setClosedPanels(_closePanel('browser'))} />
                        )}
                        {showDesktop && (
                            <DesktopPreview visible={showDesktop} onClose={() => setClosedPanels(_closePanel('desktop'))} />
                        )}
                        {showTerminal && (
                            <TerminalPanel lines={terminalLines} onClose={() => setClosedPanels(_closePanel('terminal'))} />
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
            {nudgeToast && (
                <div className={styles.nudgeToast}>{nudgeToast}</div>
            )}
        </>
    );
}
