import { useRef, useEffect, useCallback } from 'react';

/**
 * Auto-scroll a container to the bottom when dependencies change,
 * unless the user has manually scrolled up.
 *
 * @param {Array} deps — Dependency array that triggers a scroll check.
 * @param {boolean} [enabled=true] — Whether auto-scroll is active (e.g. only when agent is running).
 * @returns {{ ref, onScroll, resetScroll }}
 *   - ref: Attach to the scrollable container element.
 *   - onScroll: Attach as the container's onScroll handler.
 *   - resetScroll: Call to re-enable auto-scroll (e.g. when switching views).
 */
export default function useAutoScroll(deps, enabled = true) {
    const ref = useRef(null);
    const userScrolledRef = useRef(false);

    const onScroll = useCallback(() => {
        const el = ref.current;
        if (!el) return;
        const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 150;
        userScrolledRef.current = !nearBottom;
    }, []);

    const resetScroll = useCallback(() => {
        userScrolledRef.current = false;
    }, []);

    useEffect(() => {
        if (!enabled || userScrolledRef.current) return;
        const el = ref.current;
        if (!el) return;
        el.scrollTop = el.scrollHeight;
    }, deps); // eslint-disable-line react-hooks/exhaustive-deps

    return { ref, onScroll, resetScroll };
}
