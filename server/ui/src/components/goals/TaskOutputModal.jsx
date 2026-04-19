import { useState, useEffect } from 'react';
import MarkdownContent from '../MarkdownContent.jsx';
import styles from './TaskOutputModal.module.css';

/**
 * Full-screen modal for viewing task output with copy functionality.
 */
export default function TaskOutputModal({ output, taskName, runNumber, onClose }) {
    const [copied, setCopied] = useState(false);
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
                            {copied ? <><i className="bi bi-check-lg" /> Copied</> : <><i className="bi bi-clipboard" /> Copy</>}
                        </button>
                        <button
                            className={styles.closeBtn}
                            onClick={onClose}
                        >
                            <i className="bi bi-x-lg" />
                        </button>
                    </div>
                </div>
                <div className={styles.content}>
                    {output ? <MarkdownContent>{output}</MarkdownContent> : <p>No output</p>}
                </div>
            </div>
        </div>
    );
}
