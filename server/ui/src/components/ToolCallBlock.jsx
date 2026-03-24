import styles from './ToolCallBlock.module.css';

/** Shared tool call badge — wrench icon + tool name. */
export default function ToolCallBlock({ name }) {
    return (
        <div className={styles.toolBlock}>
            <svg className={styles.toolIcon} width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z" />
            </svg>
            <span className={styles.toolName}>{name}</span>
        </div>
    );
}
