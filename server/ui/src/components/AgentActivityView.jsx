import React, { useState, useEffect, useRef } from 'react';
import { useAgentState, useAgentDispatch } from '../hooks/useAgentState.jsx';
import { formatAgentName } from './AgentCard.jsx';
import { formatElapsed } from '../utils/agentUtils.js';
import ChevronIcon from './icons/ChevronIcon.jsx';
import MarkdownContent from './MarkdownContent.jsx';
import FileOutput from './FileOutput.jsx';
import BrowserPreview from './BrowserPreview.jsx';
import TerminalPanel from './TerminalOutput.jsx';
import DesktopPreview from './DesktopPreview.jsx';
import GenerationPreview from './GenerationPreview.jsx';
import styles from './AgentActivityView.module.css';

/**
 * Build a breadcrumb trail from root to this agent.
 */
function _buildBreadcrumb(agents, agentId) {
    const trail = [];
    let current = agentId;
    while (current && agents[current]) {
        trail.unshift(agents[current]);
        current = agents[current].parentId;
    }
    return trail;
}

/**
 * Render a single activity log entry.
 */
function ThinkingEntry({ text }) {
    const [expanded, setExpanded] = useState(true);
    return (
        <div className={`${styles.thinkBlock} ${expanded ? styles.thinkExpanded : ''}`}>
            <div className={styles.thinkHeader} onClick={() => setExpanded((e) => !e)}>
                <span>{expanded ? 'Hide thoughts' : 'Show thoughts'}</span>
                <ChevronIcon size={12} direction={expanded ? 'up' : 'down'} />
            </div>
            {expanded && (
                <div className={styles.thinkBody}>
                    <MarkdownContent>{text}</MarkdownContent>
                </div>
            )}
        </div>
    );
}

function ActivityEntry({ entry }) {
    if (entry.type === 'thinking') {
        return <ThinkingEntry text={entry.thinking} />;
    }

    if (entry.type === 'content') {
        return (
            <div className={styles.contentBlock}>
                <MarkdownContent>{entry.content}</MarkdownContent>
            </div>
        );
    }

    if (entry.type === 'tool_call') {
        return (
            <div className={styles.toolBlock}>
                <svg className={styles.toolIcon} width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z" />
                </svg>
                <span className={styles.toolName}>{entry.name}</span>
            </div>
        );
    }

    if (entry.type === 'file_output') {
        return (
            <FileOutput item={entry} />
        );
    }

    return null;
}

export default function AgentActivityView({ onNudge }) {
    const { agents, selectedAgentId } = useAgentState();
    const dispatch = useAgentDispatch();
    const scrollRef = useRef(null);

    const agent = selectedAgentId ? agents[selectedAgentId] : null;

    // Auto-scroll when agent is running
    useEffect(() => {
        if (agent?.status === 'running' && scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [agent?.activityLog?.length, agent?.status]);

    if (!agent) return null;

    const breadcrumb = _buildBreadcrumb(agents, selectedAgentId);
    const statusClass = styles[agent.status] || '';

    return (
        <div className={styles.container}>
            {/* Agent header with back button */}
            <div className={styles.agentBar}>
                <div className={styles.backRow}>
                    <button
                        className={styles.backBtn}
                        onClick={() => dispatch({ type: 'SELECT_AGENT', agentId: null })}
                    >
                        &larr; Agents
                    </button>
                    <span className={styles.breadcrumb}>
                        {breadcrumb.map((a, i) => (
                            <span key={a.id}>
                                {i > 0 && ' \u203A '}
                                <span className={i === breadcrumb.length - 1 ? styles.breadcrumbCurrent : ''}>
                                    {formatAgentName(a.name)}
                                </span>
                            </span>
                        ))}
                    </span>
                </div>
                <div className={styles.titleRow}>
                    <span className={`${styles.dot} ${statusClass}`} />
                    <span className={styles.title}>{formatAgentName(agent.name)}</span>
                    <div className={styles.meta}>
                        {agent.startedAt && <span>{formatElapsed(agent.startedAt)}</span>}
                        {agent.iteration !== null && agent.maxIterations > 0 && (
                            <span>iter {agent.iteration}/{agent.maxIterations}</span>
                        )}
                        {agent.childIds.length > 0 && (
                            <span>{agent.childIds.length} sub-agent{agent.childIds.length !== 1 ? 's' : ''}</span>
                        )}
                        {agent.activeTool && <span>{agent.activeTool}</span>}
                    </div>
                </div>
            </div>

            {/* Two-pane body */}
            <div className={styles.body}>
                {/* Activity stream */}
                <div className={styles.activity} ref={scrollRef}>
                    {agent.instruction && (
                        <div className={styles.instruction}>
                            <span className={styles.instructionLabel}>Instruction</span>
                            {agent.instruction}
                        </div>
                    )}
                    {agent.activityLog.map((entry, i) => (
                        <ActivityEntry key={i} entry={entry} />
                    ))}
                    {agent.status === 'running' && (
                        <span className={styles.cursor} />
                    )}
                </div>

                {/* Preview panels */}
                <div className={styles.previews}>
                    {agent.browserSnapshot && (
                        <BrowserPreview
                            snapshot={agent.browserSnapshot}
                            onClose={() => {}}
                        />
                    )}
                    {agent.terminalLines.length > 0 && (
                        <TerminalPanel
                            lines={agent.terminalLines}
                            onClose={() => {}}
                        />
                    )}
                    {agent.desktopActive && (
                        <DesktopPreview visible={true} onClose={() => {}} />
                    )}
                    {agent.generationPreview && (
                        <GenerationPreview
                            preview={agent.generationPreview}
                            onClose={() => {}}
                        />
                    )}
                </div>
            </div>

            {/* Nudge bar */}
            <div className={styles.nudgeBar}>
                <span className={styles.nudgeLabel}>Nudge</span>
                <input
                    className={styles.nudgeInput}
                    type="text"
                    placeholder="Send a nudge to root agent..."
                    onKeyDown={(e) => {
                        if (e.key === 'Enter' && e.target.value.trim()) {
                            if (onNudge) onNudge(e.target.value.trim());
                            e.target.value = '';
                        }
                    }}
                />
                <span className={styles.nudgeHint}>queues for root agent</span>
            </div>
        </div>
    );
}
