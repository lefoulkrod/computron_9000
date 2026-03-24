/**
 * Merge a terminal output event into the lines array.
 * If we already have output for this command, append to it.
 * Otherwise add a new entry. Keeps at most maxLines.
 */
export function mergeTerminalEvent(prev, event, maxLines = 50) {
    const lines = [...prev];
    const idx = lines.findIndex((e) => e.cmd_id === event.cmd_id);
    if (idx !== -1) {
        if (event.status === 'streaming') {
            const existing = lines[idx];
            lines[idx] = {
                ...existing,
                status: 'streaming',
                stdout: (existing.stdout || '') + (event.stdout || '') || null,
                stderr: (existing.stderr || '') + (event.stderr || '') || null,
            };
        } else {
            lines[idx] = event;
        }
    } else {
        lines.push(event);
    }
    return lines.length > maxLines ? lines.slice(-maxLines) : lines;
}

/**
 * Format elapsed time from a start timestamp to now.
 */
export function formatElapsed(startedAt) {
    if (!startedAt) return null;
    const seconds = Math.floor((Date.now() - startedAt) / 1000);
    if (seconds < 60) return `${seconds}s`;
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs}s`;
}
