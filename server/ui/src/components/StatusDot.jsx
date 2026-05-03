import styles from './StatusDot.module.css';

const STATUS_ALIAS = {
    success: 'complete',
    stopped: 'idle',
    connected: 'ready',
    disconnected: 'error',
    completed: 'complete',
    failed: 'error',
};

export default function StatusDot({ status }) {
    const resolved = STATUS_ALIAS[status] || status;
    return <span className={`${styles.dot} ${styles[resolved] || ''}`} />;
}
