import React from 'react';
import styles from './Message.module.css';
import MarkdownContent from './MarkdownContent.jsx';
import AgentOutput from './AgentOutput.jsx';
import ThinkingPlaceholder from './ThinkingPlaceholder.jsx';

/**
 * One assistant message. Uses AgentOutput for the actual content rendering
 * (same component the activity view uses). The only additions here are
 * the layout wrapper and the "Thinking..." placeholder.
 */
function AssistantMessage({ entries, onPreview, streaming }) {
    const hasEntries = entries && entries.length > 0;
    return (
        <div className={`${styles.message} ${styles.assistant}`} data-testid="message-assistant">
            <div className={styles.bubble}>
                {!hasEntries && <ThinkingPlaceholder />}
                {hasEntries && (
                    <AgentOutput
                        entries={entries}
                        streaming={streaming}
                        onPreview={onPreview}
                    />
                )}
            </div>
        </div>
    );
}

function UserMessage({ content, images, files }) {
    return (
        <div className={`${styles.message} ${styles.user}`} data-testid="message-user">
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

export default function Message(props) {
    return props.role === 'assistant' ? (
        <AssistantMessage {...props} />
    ) : (
        <UserMessage {...props} />
    );
}
