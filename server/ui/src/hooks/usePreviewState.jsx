import { useState, useMemo, useEffect, useCallback } from 'react';
import BrowserIcon from '../components/icons/BrowserIcon.jsx';
import FileIcon from '../components/icons/FileIcon.jsx';
import TerminalIcon from '../components/icons/TerminalIcon.jsx';
import DesktopIcon from '../components/icons/DesktopIcon.jsx';
import SparkleIcon from '../components/icons/SparkleIcon.jsx';

export default function usePreviewState(agentState, agentDispatch) {
    const [activeTab, setActiveTab] = useState(null);
    const [splitPosition, setSplitPosition] = useState(40);
    const [fullscreenItem, setFullscreenItem] = useState(null);

    const rootAgent = agentState.rootId ? agentState.agents[agentState.rootId] : null;
    const selectedAgentId = agentState.selectedAgentId;
    const previewAgent = (selectedAgentId && agentState.agents[selectedAgentId]) || rootAgent;

    const browserSnapshot = previewAgent?.browserSnapshot || null;
    const terminalLines = previewAgent?.terminalLines || [];
    const desktopActive = previewAgent?.desktopActive || false;
    const generationPreview = previewAgent?.generationPreview || null;
    const openFiles = previewAgent?.openFiles || [];

    const tabs = useMemo(() => {
        const t = [];
        if (browserSnapshot) t.push({ id: 'browser', label: 'Browser', icon: <BrowserIcon size={14} /> });
        for (const f of openFiles) {
            t.push({ id: `file:${f.filename}`, label: f.filename || 'File', icon: <FileIcon size={14} /> });
        }
        if (terminalLines.length > 0) t.push({ id: 'terminal', label: 'Terminal', icon: <TerminalIcon size={14} /> });
        if (desktopActive) t.push({ id: 'desktop', label: 'Desktop', icon: <DesktopIcon size={14} /> });
        if (generationPreview) t.push({ id: 'generation', label: 'Generation', icon: <SparkleIcon size={14} /> });
        return t;
    }, [browserSnapshot, openFiles, terminalLines, desktopActive, generationPreview]);

    useEffect(() => {
        if (tabs.length === 0) {
            setActiveTab(null);
        } else if (!tabs.some(t => t.id === activeTab)) {
            setActiveTab(tabs[tabs.length - 1].id);
        }
    }, [tabs, activeTab]);

    const activeFile = activeTab?.startsWith('file:')
        ? openFiles.find(f => f.filename === activeTab.slice(5))
        : null;

    const openFile = useCallback((item) => {
        const agentId = previewAgent?.id;
        if (!agentId) return;
        agentDispatch({ type: 'OPEN_FILE', agentId, item });
        setActiveTab(`file:${item.filename}`);
    }, [previewAgent?.id, agentDispatch]);

    const closeTab = useCallback((id) => {
        const agentId = previewAgent?.id;
        if (!agentId) return;

        if (id === 'browser') {
            agentDispatch({ type: 'UPDATE_BROWSER_SNAPSHOT', agentId, snapshot: null });
        } else if (id.startsWith('file:')) {
            agentDispatch({ type: 'CLOSE_FILE', agentId, filename: id.slice(5) });
        } else if (id === 'terminal') {
            agentDispatch({ type: 'CLEAR_TERMINAL', agentId });
        } else if (id === 'desktop') {
            agentDispatch({ type: 'UPDATE_DESKTOP_ACTIVE', agentId: null });
        } else if (id === 'generation') {
            agentDispatch({ type: 'UPDATE_GENERATION_PREVIEW', agentId, preview: null });
        }

        const remaining = tabs.filter(t => t.id !== id);
        setActiveTab(remaining.length > 0 ? remaining[remaining.length - 1].id : null);
    }, [tabs, previewAgent?.id, agentDispatch]);

    const reset = useCallback(() => {
        setActiveTab(null);
        setFullscreenItem(null);
    }, []);

    return {
        tabs,
        activeTab,
        setActiveTab,
        splitPosition,
        setSplitPosition,
        fullscreenItem,
        setFullscreenItem,
        activeFile,
        openFile,
        closeTab,
        reset,
        browserSnapshot,
        terminalLines,
        desktopActive,
        generationPreview,
        openFiles,
        previewAgent,
        rootAgent,
    };
}
