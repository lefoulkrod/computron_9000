import React, { memo } from 'react';
import { formatElapsed } from '../utils/agentUtils.js';
import StatusDot from './StatusDot.jsx';
import styles from './AgentCard.module.css';

function formatAgentName(name) {
    if (!name) return 'Agent';
    return name
        .replace(/_/g, ' ')
        .replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * One card in the agent network graph. Shows the agent's name, status,
 * browser thumbnail (if any), and stats. Click to drill into the
 * agent's full activity view.
 *
 * Memoized — only re-renders when something visible changes.
 */
function AgentCard({ agent, onClick }) {
    const toolCallCount = agent.activityLog
        ? agent.activityLog.filter((e) => e.type === 'tool_call').length
        : 0;

    return (
        <div
            className={styles.card}
            onClick={() => onClick(agent.id)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === 'Enter' && onClick(agent.id)}
        >
            <div className={styles.header}>
                <StatusDot status={agent.status} />
                <span className={styles.name}>{formatAgentName(agent.name)}</span>
            </div>

            {agent.browserSnapshot && (
                <div className={styles.thumbRow}>
                    <img
                        className={styles.thumb}
                        src={`data:image/png;base64,${agent.browserSnapshot.screenshot}`}
                        alt=""
                    />
                </div>
            )}

            <div className={styles.meta}>
                {agent.childIds.length > 0 && (
                    <span className={`${styles.badge} ${styles.agents}`}>
                        {agent.childIds.length} sub-agent{agent.childIds.length !== 1 ? 's' : ''}
                    </span>
                )}
                {toolCallCount > 0 && (
                    <span className={`${styles.badge} ${styles.iter}`}>
                        {toolCallCount} tool{toolCallCount !== 1 ? 's' : ''}
                    </span>
                )}
                {agent.startedAt && (
                    <span className={`${styles.badge} ${styles.time}`}>
                        {formatElapsed(agent.startedAt, agent.completedAt)}
                    </span>
                )}
            </div>
        </div>
    );
}

export default memo(AgentCard, (prev, next) => {
    const a = prev.agent, b = next.agent;
    return (
        a.status === b.status &&
        a.activeTool === b.activeTool &&
        a.childIds.length === b.childIds.length &&
        a.browserSnapshot === b.browserSnapshot &&
        a.startedAt === b.startedAt &&
        a.activityLog.length === b.activityLog.length
    );
});

export { formatAgentName };
