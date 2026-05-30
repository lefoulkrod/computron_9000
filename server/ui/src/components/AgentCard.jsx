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

            {(() => {
                // Card-level thumbnail.  With one tab, show its screenshot;
                // with several, layer up to three tabs as an offset card
                // stack so the user reads "this agent has multiple tabs open"
                // at a glance.  Top of the stack is whichever tab most
                // recently got a new snapshot — that's what the agent was
                // last doing.
                const tabs = agent.browserTabs || {};
                const lastKey = agent.lastBrowserTabId;
                const withScreens = Object.entries(tabs).filter(([, s]) => s?.screenshot);
                // Pull the most-recently-updated tab to the front; siblings
                // sit behind it in tab-id order so the back of the stack is
                // stable as new snapshots arrive.
                const head = withScreens.find(([k]) => String(k) === String(lastKey));
                const rest = withScreens
                    .filter(([k]) => String(k) !== String(lastKey))
                    .sort(([a], [b]) => {
                        const ai = a === 'untracked' ? -Infinity : Number(a);
                        const bi = b === 'untracked' ? -Infinity : Number(b);
                        return ai - bi;
                    });
                const ordered = head ? [head, ...rest] : rest;
                const sorted = ordered.slice(0, 3).map(([k, snap]) => ({ key: k, snap }));
                if (sorted.length === 0) return null;
                if (sorted.length === 1) {
                    return (
                        <div className={styles.thumbRow}>
                            <img
                                className={styles.thumb}
                                src={`data:image/png;base64,${sorted[0].snap.screenshot}`}
                                alt=""
                            />
                        </div>
                    );
                }
                return (
                    <div className={styles.thumbRow}>
                        <div
                            className={styles.thumbStack}
                            data-count={sorted.length}
                        >
                            {/* Render back-to-front so DOM order matches z-order. */}
                            {sorted.slice().reverse().map(({ key, snap }) => (
                                <img
                                    key={key}
                                    className={styles.stackedThumb}
                                    src={`data:image/png;base64,${snap.screenshot}`}
                                    alt=""
                                />
                            ))}
                        </div>
                    </div>
                );
            })()}

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
        a.browserTabs === b.browserTabs &&
        a.lastBrowserTabId === b.lastBrowserTabId &&
        a.startedAt === b.startedAt &&
        a.activityLog.length === b.activityLog.length
    );
});

export { formatAgentName };
