import { useEffect } from 'react';
import { useAgentState, useAgentDispatch } from '../hooks/useAgentState.jsx';
import useAutoScroll from '../hooks/useAutoScroll.js';
import { formatAgentName } from './AgentCard.jsx';
import { formatElapsed } from '../utils/agentUtils.js';
import ContextUsageBadge from './ContextUsageBadge.jsx';
import AgentOutput from './AgentOutput.jsx';
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
 * Full-screen view of a single agent's work. Two panes:
 *   Left: activity stream (thinking, text, tool calls) — auto-scrolls
 *   Right: preview panels (browser, terminal, files) scoped to this agent
 *
 * The nudge bar at the bottom always sends to the root agent.
 * "← Agents" goes back to the network graph.
 */
export default function AgentActivityView({ onNudge, onPreview }) {
    const { agents, selectedAgentId } = useAgentState();
    const dispatch = useAgentDispatch();
    const agent = selectedAgentId ? agents[selectedAgentId] : null;

    const { ref: scrollRef, onScroll: handleScroll, resetScroll } = useAutoScroll(
        [agent?.activityLog?.length, agent?.status],
        agent?.status === 'running',
    );

    // Reset scroll lock when switching agents
    useEffect(() => {
        resetScroll();
    }, [selectedAgentId, resetScroll]);

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
                        {agent.iteration !== null && (
                            <span>
                                iter {agent.iteration}{agent.maxIterations ? `/${agent.maxIterations}` : ''}
                            </span>
                        )}
                        <ContextUsageBadge contextUsage={agent.contextUsage} />
                        {agent.childIds.length > 0 && (
                            <span>{agent.childIds.length} sub-agent{agent.childIds.length !== 1 ? 's' : ''}</span>
                        )}
                    </div>
                </div>
            </div>

            {/* Two-pane body */}
            <div className={styles.body}>
                {/* Activity stream */}
                <div className={styles.activity} ref={scrollRef} onScroll={handleScroll}>
                    {agent.instruction && (
                        <div className={styles.instruction}>
                            <span className={styles.instructionLabel}>Instruction</span>
                            <MarkdownContent>{agent.instruction}</MarkdownContent>
                        </div>
                    )}
                    <AgentOutput
                        entries={agent.activityLog}
                        showFileOutputs={false}
                    />
                    {agent.status === 'running' && (
                        <span className={styles.cursor} />
                    )}
                </div>

                {/* Preview panels */}
                <div className={styles.previews}>
                    {agent.browserSnapshot && (
                        <BrowserPreview
                            snapshot={agent.browserSnapshot}
                        />
                    )}
                    {agent.terminalLines.length > 0 && (
                        <TerminalPanel
                            lines={agent.terminalLines}
                        />
                    )}
                    {agent.desktopActive && (
                        <DesktopPreview visible={true} />
                    )}
                    {agent.generationPreview && (
                        <GenerationPreview
                            preview={agent.generationPreview}
                        />
                    )}
                    {agent.activityLog
                        .filter((e) => e.type === 'file_output')
                        .map((entry, i) => (
                            <FileOutput key={`file-${i}`} item={entry} onPreview={onPreview} />
                        ))
                    }
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
