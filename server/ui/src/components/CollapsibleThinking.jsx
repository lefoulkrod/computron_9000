import React, { useEffect, useRef, useState } from 'react';
import ChevronIcon from './icons/ChevronIcon.jsx';
import MarkdownContent from './MarkdownContent.jsx';
import styles from './CollapsibleThinking.module.css';

/**
 * Collapsible thinking block used in both the chat view and the agent
 * activity view. It stays open while the agent is still thinking, then
 * auto-collapses once the agent moves on — unless the reader has
 * expanded or collapsed it themselves, in which case their choice sticks.
 *
 * @param {string} text — The thinking text to render as markdown.
 * @param {boolean} [compact=false] — Smaller, more subdued styling (activity view).
 * @param {boolean} [streaming=false] — Whether this block is still streaming.
 */
export default function CollapsibleThinking({ text, compact = false, streaming = false }) {
    // Live thinking starts open; a finished block (e.g. from a resumed
    // conversation) starts closed.
    const [expanded, setExpanded] = useState(streaming);
    const userToggled = useRef(false);
    const wasStreaming = useRef(streaming);

    // When streaming ends, collapse — unless the reader has taken control.
    useEffect(() => {
        if (wasStreaming.current && !streaming && !userToggled.current) {
            setExpanded(false);
        }
        wasStreaming.current = streaming;
    }, [streaming]);

    if (!text) return null;

    const toggle = () => {
        userToggled.current = true;
        setExpanded((e) => !e);
    };

    const label = streaming ? 'Thinking…' : expanded ? 'Hide thinking' : 'Show thinking';

    return (
        <div className={`${styles.block} ${expanded ? styles.expanded : ''} ${compact ? styles.compact : ''}`} data-testid="entry-thinking">
            <div className={styles.header} onClick={toggle} data-testid="thinking-toggle">
                <span>{label}</span>
                <ChevronIcon size={12} direction={expanded ? 'up' : 'down'} />
            </div>
            {expanded && (
                <div className={styles.body}>
                    <MarkdownContent streaming={streaming}>{text}</MarkdownContent>
                </div>
            )}
        </div>
    );
}
