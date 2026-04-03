/**
 * Shared utilities for goal UI components.
 */

const _DAYS_FULL = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const _DAYS_SHORT = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function _formatTime(hour, min) {
    const h = parseInt(hour, 10);
    const m = parseInt(min, 10);
    if (isNaN(h) || isNaN(m)) return null;
    const ampm = h < 12 ? 'AM' : 'PM';
    const h12 = h % 12 || 12;
    return m === 0 ? `${h12} ${ampm}` : `${h12}:${String(m).padStart(2, '0')} ${ampm}`;
}

function _isSimple(part) {
    return /^\d+$/.test(part);
}

/** Convert a 5-part cron expression to a human-readable string. Falls back to the raw expr. */
export function formatCron(expr) {
    if (!expr) return null;
    const parts = expr.trim().split(/\s+/);
    if (parts.length !== 5) return expr;
    const [min, hour, dom, month, dow] = parts;

    // Every N minutes: */N * * * *
    if (/^\*\/\d+$/.test(min) && hour === '*' && dom === '*' && month === '*' && dow === '*') {
        const n = parseInt(min.slice(2), 10);
        return n === 1 ? 'Every minute' : `Every ${n} minutes`;
    }

    // Every N hours: 0 */N * * *
    if (min === '0' && /^\*\/\d+$/.test(hour) && dom === '*' && month === '*' && dow === '*') {
        const n = parseInt(hour.slice(2), 10);
        return n === 1 ? 'Every hour' : `Every ${n} hours`;
    }

    // Need a fixed time for remaining patterns
    if (!_isSimple(min) || !_isSimple(hour)) return expr;
    const time = _formatTime(hour, min);
    if (!time) return expr;

    // Every day: 0 H * * *
    if (dom === '*' && month === '*' && dow === '*') {
        return `Daily at ${time}`;
    }

    // Specific weekday(s): 0 H * * D
    if (dom === '*' && month === '*' && dow !== '*') {
        if (dow === '1-5') return `Weekdays at ${time}`;
        if (dow === '0,6' || dow === '6,0') return `Weekends at ${time}`;
        if (_isSimple(dow)) {
            const d = parseInt(dow, 10);
            if (d >= 0 && d <= 6) return `Every ${_DAYS_FULL[d]} at ${time}`;
        }
        // Multiple specific days: 0 H * * 1,3,5
        if (/^[\d,]+$/.test(dow)) {
            const days = dow.split(',').map(Number);
            if (days.every(d => d >= 0 && d <= 6)) {
                return `${days.map(d => _DAYS_SHORT[d]).join('/')} at ${time}`;
            }
        }
    }

    // Specific day of month: 0 H D * *
    if (_isSimple(dom) && month === '*' && dow === '*') {
        const d = parseInt(dom, 10);
        const suffix = d === 1 ? 'st' : d === 2 ? 'nd' : d === 3 ? 'rd' : 'th';
        return `Monthly on the ${d}${suffix} at ${time}`;
    }

    return expr;
}

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
