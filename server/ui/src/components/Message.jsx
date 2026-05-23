import React from 'react';
import styles from './Message.module.css';
import MarkdownContent from './MarkdownContent.jsx';
import AgentOutput from './AgentOutput.jsx';
import AttachmentChip from './AttachmentChip.jsx';
import ThinkingPlaceholder from './ThinkingPlaceholder.jsx';

/**
 * One assistant message. Uses AgentOutput for the actual content rendering
 * (same component the activity view uses). When the turn spawned
 * sub-agents, AgentOutput renders a SpawnCard inline at each spawn
 * request so the card flows with the surrounding output.
 */
function AssistantMessage({ entries, onPreview, streaming, spawnedAgents, onSelectAgent }) {
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
                        spawnedAgents={spawnedAgents}
                        onSelectAgent={onSelectAgent}
                    />
                )}
            </div>
        </div>
    );
}

function UserMessage({ content, images, files }) {
    const imageList = Array.isArray(images) ? images : [];
    const fileList = Array.isArray(files) ? files : [];
    const hasAttachments = imageList.length > 0 || fileList.length > 0;
    return (
        <div className={`${styles.message} ${styles.user}`} data-testid="message-user">
            <div className={styles.bubble}>
                {hasAttachments && (
                    <div className={styles.attachments}>
                        {imageList.map((src, i) => (
                            <AttachmentChip key={`img-${i}`} src={src} />
                        ))}
                        {fileList.map((f, i) => (
                            <AttachmentChip key={`file-${i}`} filename={f.filename} />
                        ))}
                    </div>
                )}
                {content && <MarkdownContent>{content}</MarkdownContent>}
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
