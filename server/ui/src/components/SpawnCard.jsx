import StatusDot from './StatusDot.jsx';
import { formatAgentName } from './AgentCard.jsx';
import styles from './SpawnCard.module.css';

function _fmtTokens(n) {
    if (n == null) return null;
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
    return String(n);
}

/** Status counts for the card header — running / done / error. */
function _rollup(agents) {
    let running = 0;
    let done = 0;
    let error = 0;
    for (const a of agents) {
        if (a.status === 'running') running += 1;
        else if (a.status === 'error') error += 1;
        else done += 1; // success, stopped
    }
    return [
        running && `${running} running`,
        done && `${done} done`,
        error && `${error} error`,
    ].filter(Boolean).join(' · ');
}

/** Per-row meta — iteration and context fill, whichever are known. */
function _meta(agent) {
    const parts = [];
    if (agent.iteration != null) {
        parts.push(`iter ${agent.iteration}${agent.maxIterations ? `/${agent.maxIterations}` : ''}`);
    }
    const ctx = agent.contextUsage;
    if (ctx && ctx.context_limit) {
        parts.push(`${_fmtTokens(ctx.context_used)} / ${_fmtTokens(ctx.context_limit)}`);
    }
    return parts.join(' · ');
}

/**
 * Grouped card for the sub-agents a turn spawned. Renders one clickable
 * row per agent — bound to live agent state — that opens that agent's
 * activity view. Replaces the raw spawn_agent tool-call lines.
 */
export default function SpawnCard({ agents, onSelectAgent }) {
    if (!agents || agents.length === 0) return null;
    return (
        <div className={styles.card} data-testid="spawn-card">
            <div className={styles.header}>
                <i className="bi bi-diagram-3" />
                <span className={styles.title}>
                    spawn_agent · {agents.length} agent{agents.length !== 1 ? 's' : ''}
                </span>
                <span className={styles.rollup}>{_rollup(agents)}</span>
            </div>
            {agents.map((agent) => {
                const meta = _meta(agent);
                return (
                    <button
                        key={agent.id}
                        type="button"
                        className={styles.row}
                        onClick={() => onSelectAgent?.(agent.id)}
                        data-testid="spawn-card-row"
                        data-agent-id={agent.id}
                    >
                        <StatusDot status={agent.status} />
                        <span className={styles.name}>{formatAgentName(agent.name)}</span>
                        {meta && <span className={styles.meta}>{meta}</span>}
                        <i className={`bi bi-chevron-right ${styles.chev}`} />
                    </button>
                );
            })}
        </div>
    );
}
