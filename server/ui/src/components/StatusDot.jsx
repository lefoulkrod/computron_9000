import styles from './StatusDot.module.css';

/**
 * Colored status dot indicating agent state.
 * Pulses when running, static otherwise.
 */
export default function StatusDot({ status }) {
    return <span className={`${styles.dot} ${styles[status] || ''}`} />;
}
