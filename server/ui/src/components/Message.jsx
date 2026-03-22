import React, { useRef, useState } from 'react';
import styles from './Message.module.css';
import ChevronIcon from './icons/ChevronIcon.jsx';
import MarkdownContent from './MarkdownContent.jsx';
import ToolCallsSummary from './ToolCallsSummary';
import FileOutput from './FileOutput.jsx';
import { formatAgentName } from './AgentCard.jsx';

function ContextUsageBadge({ contextUsage }) {
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

function AssistantMessage({ content, thinking, images, placeholder, agent_name, depth = 0, data, contextUsage, onPreview, streaming }) {
    const [thinkingExpanded, setThinkingExpanded] = useState(true);
    const bubbleRef = useRef(null);
    const displayName = formatAgentName(agent_name);

    const toolCalls = Array.isArray(data)
        ? data.filter(item => item && item.type === 'tool_call')
        : [];

    const fileOutputs = Array.isArray(data)
        ? data.filter(item => item && item.type === 'file_output')
        : [];


    return (
        <div
            className={`${styles.message} ${styles.assistant} ${depth > 0 ? styles.subAgent : ''}`}
            style={{ '--depth-level': depth }}
        >
            <div className={styles.bubble} ref={bubbleRef}>
                {!placeholder && (agent_name || toolCalls.length > 0 || contextUsage) && (
                    <div className={styles.messageHeader}>
                        {agent_name && (
                            <span className={styles.agentLabel}>
                                {depth > 0 && '↳ '}{displayName}
                            </span>
                        )}
                        <ContextUsageBadge contextUsage={contextUsage} />
                        {agent_name && toolCalls.length > 0 && ' — '}
                        <ToolCallsSummary toolCalls={toolCalls} />
                    </div>
                )}
                {placeholder && (
                    <div className={styles.loadingIndicator}>
                        Thinking<span className={styles.dot}>.</span>
                        <span className={styles.dot}>.</span>
                        <span className={styles.dot}>.</span>
                    </div>
                )}
                {!placeholder && thinking && (
                    <div
                        className={`${styles.collapsibleThink} ${thinkingExpanded ? styles.expanded : ''}`}
                    >
                        <div
                            className={styles.collapsibleThinkHeader}
                            onClick={() => setThinkingExpanded((e) => !e)}
                        >
                            <span>{thinkingExpanded ? 'Hide thoughts' : 'Show thoughts'}</span>
                            <ChevronIcon size={12} direction={thinkingExpanded ? 'up' : 'down'} />
                        </div>
                        {thinkingExpanded && (
                            <div className={styles.collapsibleThinkContent}>
                                <MarkdownContent streaming={streaming}>{thinking}</MarkdownContent>
                            </div>
                        )}
                    </div>
                )}
                {!placeholder && <MarkdownContent streaming={streaming}>{content}</MarkdownContent>}
                {fileOutputs.length > 0 && (
                    <div>
                        {fileOutputs.map((item, i) => (
                            <FileOutput key={i} item={item} onPreview={onPreview} />
                        ))}
                    </div>
                )}
                {Array.isArray(images) && images.length > 0 && (
                    <div className={styles.messageImages}>
                        {images.map((src, i) => (
                            <img key={i} src={src} alt={`assistant-attachment-${i}`} />
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

function UserMessage({ content, images, files }) {
    return (
        <div className={`${styles.message} ${styles.user}`}>
            <div className={styles.bubble}>
                <MarkdownContent>{content}</MarkdownContent>
                {Array.isArray(files) && files.length > 0 && (
                    <div className={styles.userFiles}>
                        {files.map((f, i) => (
                            <div key={i} className={styles.userFileChip}>
                                <span>📎</span>
                                <span>{f.filename}</span>
                            </div>
                        ))}
                    </div>
                )}
                {Array.isArray(images) && images.length > 0 && (
                    <div className={styles.messageImages}>
                        {images.map((src, i) => (
                            <img key={i} src={src} alt={`user-attachment-${i}`} />
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

export default React.memo(function Message(props) {
    return props.role === 'assistant' ? (
        <AssistantMessage {...props} />
    ) : (
        <UserMessage {...props} />
    );
});
