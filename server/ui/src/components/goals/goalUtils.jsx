/**
 * Utility functions for Goals UI components.
 * Status icons, formatting helpers, and common patterns.
 */

// Status Icon component (reused across goals)
export function StatusIcon({ status, size = 14 }) {
    const color = {
        active: 'var(--text)',
        completed: '#4ade80',
        running: '#22d3ee',
        failed: '#f87171',
        pending: 'var(--muted)',
        paused: '#fbbf24',
    }[status] || 'var(--muted)';

    return (
        <svg width={size} height={size} viewBox="0 0 14 14" fill={color}>
            <circle cx="7" cy="7" r="6" stroke="none" />
        </svg>
    );
}

// Format a timestamp relative to now (e.g., "2h ago")
export function formatTime(timestamp) {
    if (!timestamp) return '-';
    
    const date = typeof timestamp === 'string' ? new Date(timestamp) : new Date(timestamp * 1000);
    const now = new Date();
    const diffMs = now - date;
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);

    if (diffSec < 60) return 'just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    if (diffHour < 24) return `${diffHour}h ago`;
    if (diffDay < 7) return `${diffDay}d ago`;
    
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

// Format duration between two timestamps
export function formatDuration(start, end) {
    if (!start || !end) return null;
    
    const startMs = typeof start === 'string' ? new Date(start).getTime() : start * 1000;
    const endMs = typeof end === 'string' ? new Date(end).getTime() : end * 1000;
    const diffSec = Math.floor((endMs - startMs) / 1000);
    
    if (diffSec < 60) return `${diffSec}s`;
    const min = Math.floor(diffSec / 60);
    const sec = diffSec % 60;
    if (min < 60) return `${min}m ${sec}s`;
    const hour = Math.floor(min / 60);
    const remMin = min % 60;
    return `${hour}h ${remMin}m`;
}

// Format a future timestamp relative to now (e.g., "in 2h")
export function formatTimeUntil(timestamp) {
    if (!timestamp) return '-';

    const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
    const now = new Date();
    const diffMs = date - now;
    if (diffMs <= 0) return 'now';
    const diffMin = Math.floor(diffMs / 60000);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);

    if (diffMin < 1) return '<1m';
    if (diffMin < 60) return `in ${diffMin}m`;
    if (diffHour < 24) return `in ${diffHour}h ${diffMin % 60}m`;
    return `in ${diffDay}d`;
}

// Format cron expression for display (simplified)
export function formatCron(cron) {
    if (!cron) return '-';
    
    // Very basic cron formatter - shows the raw cron in a readable way
    // For a full app, you'd want a proper cron-parser library
    const parts = cron.split(' ');
    if (parts.length !== 5) return cron;

    // Common patterns
    if (cron === '0 * * * *') return 'Every hour';
    if (cron === '0 0 * * *') return 'Daily at midnight';
    if (cron === '0 */6 * * *') return 'Every 6 hours';
    if (cron === '*/15 * * * *') return 'Every 15 minutes';
    if (cron === '0 9 * * 1-5') return 'Weekdays at 9 AM';
    
    // Default: show the cron
    return cron;
}
