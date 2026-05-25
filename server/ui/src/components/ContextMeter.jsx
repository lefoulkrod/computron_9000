import styles from './ContextMeter.module.css';

// Fallback when an event predates the compaction_threshold field.
const DEFAULT_THRESHOLD = 0.75;
// Fraction of the threshold at which the meter shifts to its warning
// colour — i.e. compaction is getting close but hasn't fired yet.
const WARN_FRACTION = 0.8;

function _formatTokens(n) {
    if (n == null) return '0';
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
    return String(n);
}

/**
 * Compact context-window meter: a slim bar with a tick at the agent's
 * compaction threshold plus the numeric token count. The threshold is
 * per-profile and travels on each context-usage event, so the tick and
 * the colour shifts track whatever profile is currently active.
 */
export default function ContextMeter({ contextUsage }) {
    if (!contextUsage || !contextUsage.context_limit) return null;

    const fill = Math.min(Math.max(contextUsage.fill_ratio ?? 0, 0), 1);
    const pct = Math.round(fill * 100);
    const threshold = contextUsage.compaction_threshold ?? DEFAULT_THRESHOLD;
    const level = fill >= threshold ? 'high'
        : fill >= threshold * WARN_FRACTION ? 'med'
        : 'low';

    const used = _formatTokens(contextUsage.context_used);
    const limit = _formatTokens(contextUsage.context_limit);
    const compactionAt = Math.round(contextUsage.context_limit * threshold);

    return (
        <span
            className={`${styles.meter} ${styles[level]}`}
            data-testid="context-meter"
            data-level={level}
            title={`Context: ${contextUsage.context_used.toLocaleString()} / ${contextUsage.context_limit.toLocaleString()} tokens (${pct}%) · compaction at ${compactionAt.toLocaleString()} (${Math.round(threshold * 100)}%)`}
        >
            <span className={styles.bar}>
                <span className={styles.fill} style={{ width: `${pct}%` }} data-testid="context-meter-fill" />
                <span
                    className={styles.tick}
                    style={{ left: `${Math.min(threshold, 1) * 100}%` }}
                    data-testid="context-meter-tick"
                />
            </span>
            <span className={styles.num}>{used}</span>
            <span className={styles.pct}>/ {limit}</span>
        </span>
    );
}
