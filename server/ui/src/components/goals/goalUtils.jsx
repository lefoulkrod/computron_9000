/**
 * Shared utilities for goal UI components.
 */

export function formatTime(iso) {
    if (!iso) return '';
    try {
        const d = new Date(iso);
        const now = new Date();
        const isToday = d.toDateString() === now.toDateString();
        const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        return isToday ? `Today ${time}` : d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ` ${time}`;
    } catch { return ''; }
}

export function formatDuration(start, end) {
    if (!start || !end) return '';
    const ms = new Date(end) - new Date(start);
    const s = Math.floor(ms / 1000);
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    const rem = s % 60;
    return `${m}m ${rem}s`;
}

const STATUS_MAP = {
    completed: { char: '\u2713', color: '#4ade80', bg: 'rgba(74, 222, 128, 0.15)', border: 'rgba(74, 222, 128, 0.3)' },
    running: { char: '\u25B6', color: '#fbbf24', bg: 'rgba(251, 191, 36, 0.15)', border: 'rgba(251, 191, 36, 0.3)', nudge: '1px' },
    failed: { char: '\u2717', color: '#f87171', bg: 'rgba(248, 113, 113, 0.15)', border: 'rgba(248, 113, 113, 0.3)' },
    pending: { char: '\u2022', color: '#6b7280', bg: 'rgba(107, 114, 128, 0.15)', border: 'rgba(107, 114, 128, 0.3)' },
    active: { char: '\u2022', color: '#4ade80', bg: 'rgba(74, 222, 128, 0.15)', border: 'rgba(74, 222, 128, 0.3)' },
    paused: { char: '\u2016', color: '#a78bfa', bg: 'rgba(167, 139, 250, 0.15)', border: 'rgba(167, 139, 250, 0.3)' },
};

export function StatusIcon({ status, size = 16 }) {
    const { char, color, bg, border, nudge } = STATUS_MAP[status] || STATUS_MAP.pending;
    return (
        <div style={{
            width: size, height: size, borderRadius: '50%',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: size * 0.56, flexShrink: 0,
            background: bg, color, border: `1px solid ${border}`,
            paddingLeft: nudge || 0,
        }}>
            {char}
        </div>
    );
}
