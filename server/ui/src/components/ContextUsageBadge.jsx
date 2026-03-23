import React from 'react';
import styles from './ContextUsageBadge.module.css';

export default function ContextUsageBadge({ contextUsage }) {
    if (!contextUsage || !contextUsage.context_limit) return null;
    const pct = Math.round(contextUsage.fill_ratio * 100);
    const level = pct >= 85 ? 'high' : pct >= 70 ? 'medium' : 'low';
    // SVG donut: radius 5, circumference ≈ 31.4
    const r = 5;
    const circ = 2 * Math.PI * r;
    const filled = Math.min(pct / 100, 1) * circ;
    return (
        <span
            className={`${styles.contextBadge} ${styles[`contextBadge_${level}`]}`}
            title={`Context: ${contextUsage.context_used.toLocaleString()} / ${contextUsage.context_limit.toLocaleString()} tokens (${pct}%)`}
        >
            <svg width="14" height="14" viewBox="0 0 14 14" className={styles.contextPie}>
                <circle cx="7" cy="7" r={r} className={styles.contextPieTrack} />
                <circle
                    cx="7" cy="7" r={r}
                    className={styles.contextPieFill}
                    strokeDasharray={`${filled} ${circ}`}
                    transform="rotate(-90 7 7)"
                />
            </svg>
            {pct}%
        </span>
    );
}
