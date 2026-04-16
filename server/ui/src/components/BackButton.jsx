import styles from './BackButton.module.css';

/**
 * Small "← Label" button used for navigation in agent views.
 */
export default function BackButton({ label, onClick }) {
    return (
        <button className={styles.btn} onClick={onClick} data-testid={`back-btn-${label.toLowerCase()}`}>
            <span className={styles.arrow}>&#x2190;</span><span>{label}</span>
        </button>
    );
}
