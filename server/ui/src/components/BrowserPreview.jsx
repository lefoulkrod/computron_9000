import { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import PreviewShell from './PreviewShell.jsx';
import styles from './BrowserPreview.module.css';
import PaperclipIcon from './icons/PaperclipIcon.jsx';
import BrowserIcon from './icons/BrowserIcon.jsx';
import LockIcon from './icons/LockIcon.jsx';

function BrowserLightbox({ src, alt, onClose }) {
    const handleKey = useCallback((e) => {
        if (e.key === 'Escape') onClose();
    }, [onClose]);

    useEffect(() => {
        document.addEventListener('keydown', handleKey);
        return () => document.removeEventListener('keydown', handleKey);
    }, [handleKey]);

    return createPortal(
        <div className={styles.lightboxOverlay} onClick={onClose}>
            <img
                className={styles.lightboxImg}
                src={src}
                alt={alt}
                onClick={(e) => e.stopPropagation()}
            />
        </div>,
        document.body
    );
}

export default function BrowserPreview({ snapshot, onAttachScreenshot, onClose }) {
    const [lightboxOpen, setLightboxOpen] = useState(false);

    if (!snapshot) return null;

    const screenshotSrc = snapshot.screenshot
        ? `data:image/png;base64,${snapshot.screenshot}`
        : null;

    const attachBtn = onAttachScreenshot && snapshot.screenshot ? (
        <button
            className={styles.attachButton}
            onClick={(e) => { e.stopPropagation(); onAttachScreenshot(snapshot.screenshot); }}
            title="Attach screenshot to chat"
            aria-label="Attach screenshot to chat"
        >
            <PaperclipIcon size={14} />
        </button>
    ) : null;

    return (
        <PreviewShell
            icon={<BrowserIcon size={16} />}
            title="Browser"
            onClose={onClose}
            expandContent={screenshotSrc ? (
                <img src={screenshotSrc} alt="Browser screenshot" className={styles.expandedImg} />
            ) : undefined}
            headerExtra={attachBtn}
        >
            <div className={styles.content}>
                <div className={styles.urlBar}>
                    <LockIcon size={12} className={styles.lockIcon} />
                    <span className={styles.url} title={snapshot.url}>
                        {snapshot.url}
                    </span>
                </div>

                {snapshot.title && (
                    <div className={styles.pageTitle} title={snapshot.title}>
                        {snapshot.title}
                    </div>
                )}

                {screenshotSrc && (
                    <div
                        className={styles.screenshotContainer}
                        onClick={() => setLightboxOpen(true)}
                    >
                        <img
                            key={snapshot.screenshot.substring(0, 50)}
                            src={screenshotSrc}
                            alt="Browser screenshot"
                            className={styles.screenshot}
                        />
                    </div>
                )}
                {lightboxOpen && screenshotSrc && (
                    <BrowserLightbox
                        src={screenshotSrc}
                        alt="Browser screenshot"
                        onClose={() => setLightboxOpen(false)}
                    />
                )}
            </div>
        </PreviewShell>
    );
}
