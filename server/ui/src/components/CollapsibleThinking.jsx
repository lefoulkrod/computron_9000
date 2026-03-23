import React, { useState } from 'react';
import ChevronIcon from './icons/ChevronIcon.jsx';
import MarkdownContent from './MarkdownContent.jsx';
import styles from './CollapsibleThinking.module.css';

/**
 * Collapsible thinking block used in both the chat view and the agent activity view.
 *
 * @param {string} text — The thinking text to render as markdown.
 * @param {boolean} [compact=false] — Use smaller, more subdued styling (activity view).
 * @param {boolean} [streaming=false] — Whether the content is still streaming.
 */
export default function CollapsibleThinking({ text, compact = false, streaming = false }) {
    const [expanded, setExpanded] = useState(true);

    if (!text) return null;

    return (
        <div className={`${styles.block} ${expanded ? styles.expanded : ''} ${compact ? styles.compact : ''}`}>
            <div className={styles.header} onClick={() => setExpanded((e) => !e)}>
                <span>{expanded ? 'Hide thoughts' : 'Show thoughts'}</span>
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
