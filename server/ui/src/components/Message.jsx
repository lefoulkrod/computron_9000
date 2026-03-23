import React, { useRef } from 'react';
import styles from './Message.module.css';
import MarkdownContent from './MarkdownContent.jsx';
import CollapsibleThinking from './CollapsibleThinking.jsx';
import ToolCallsSummary from './ToolCallsSummary';
import FileOutput from './FileOutput.jsx';
import ContextUsageBadge from './ContextUsageBadge.jsx';
import { formatAgentName } from './AgentCard.jsx';

function AssistantMessage({ content, thinking, images, placeholder, agent_name, depth = 0, data, contextUsage, onPreview, streaming }) {
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
                    <CollapsibleThinking text={thinking} streaming={streaming} />
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
