import { useEffect, useCallback } from 'react';
import styles from './FullscreenPreview.module.css';
import ArrowLeftIcon from './icons/ArrowLeftIcon.jsx';

export default function FullscreenPreview({ title, onClose, headerActions, children }) {
    const handleKeyDown = useCallback((e) => {
        if (e.key === 'Escape') {
            onClose();
        }
    }, [onClose]);

    useEffect(() => {
        document.addEventListener('keydown', handleKeyDown);
        return () => document.removeEventListener('keydown', handleKeyDown);
    }, [handleKeyDown]);

    return (
        <div className={styles.fullscreenPreview} data-testid="fullscreen-preview">
            <div className={styles.header}>
                <div className={styles.headerLeft}>
                    <button
                        className={styles.backBtn}
                        onClick={onClose}
                        title="Back"
                        aria-label="Back to preview panel"
                        data-testid="fullscreen-back"
                    >
                        <ArrowLeftIcon size={14} />
                        Back
                    </button>
                </div>

                <div className={styles.headerCenter}>
                    {title && (
                        <span
                            className={styles.title}
                            title={typeof title === 'string' ? title : undefined}
                        >
                            {title}
                        </span>
                    )}
                </div>

                <div className={styles.headerRight}>
                    {headerActions}
                </div>
            </div>

            <div className={styles.content}>
                {children}
            </div>
        </div>
    );
}
