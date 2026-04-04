import { useState, useEffect } from 'react';
import styles from './TaskOutputModal.module.css';

/**
 * Full-screen modal for viewing task output with copy functionality.
 */
export default function TaskOutputModal({ output, taskName, runNumber, onClose }) {
    const [copied, setCopied] = useState(false);
    const isError = output?.toLowerCase().includes('error') || output?.toLowerCase().includes('exception');

    // Handle Escape key to close modal
    useEffect(() => {
        const handleEscape = (e) => {
            if (e.key === 'Escape') onClose();
        };
        document.addEventListener('keydown', handleEscape);
        return () => document.removeEventListener('keydown', handleEscape);
    }, [onClose]);

    const handleCopy = async () => {
        await navigator.clipboard.writeText(output);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
    };

    // Close on backdrop click
    const handleBackdropClick = (e) => {
        if (e.target === e.currentTarget) {
            onClose();
        }
    };

    return (
        <div className={styles.backdrop} onClick={handleBackdropClick}>
            <div className={styles.modal}>
                <div className={styles.header}>
                    <div className={styles.headerInfo}>
                        <div className={styles.headerTitle}>Task Output</div>
                        <div className={styles.headerSubtitle}>
                            {taskName} • Run #{runNumber}
                        </div>
                    </div>
                    <div className={styles.headerActions}>
                        <button
                            className={styles.copyBtn}
                            onClick={handleCopy}
                        >
                            {copied ? '✓ Copied' : '📋 Copy'}
                        </button>
                        <button
                            className={styles.closeBtn}
                            onClick={onClose}
                        >
                            ✕
                        </button>
                    </div>
                </div>
                <div className={`${styles.content} ${isError ? styles.error : ''}`}>
                    <pre className={styles.pre}>{output || 'No output'}</pre>
                </div>
            </div>
        </div>
    );
}
