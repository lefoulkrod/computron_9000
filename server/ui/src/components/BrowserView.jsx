import React, { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import styles from './BrowserView.module.css';
import PaperclipIcon from './icons/PaperclipIcon.jsx';
import BrowserIcon from './icons/BrowserIcon.jsx';
import ChevronIcon from './icons/ChevronIcon.jsx';
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

export default function BrowserView({ snapshot, onAttachScreenshot, onClose }) {
    const [isCollapsed, setIsCollapsed] = useState(false);
    const [lightboxOpen, setLightboxOpen] = useState(false);

    if (!snapshot) {
        return null;
    }

    const toggleCollapse = () => {
        setIsCollapsed((prev) => !prev);
    };

    return (
        <div className={styles.browserView}>
            <div className={styles.header} onClick={toggleCollapse}>
                <div className={styles.headerLeft}>
                    <BrowserIcon size={16} className={styles.browserIcon} />
                    <span className={styles.title}>Browser</span>
                </div>
                <div className={styles.headerRight}>
                    <button className={styles.collapseBtn} aria-label={isCollapsed ? 'Expand' : 'Collapse'}>
                        <ChevronIcon size={12} direction={isCollapsed ? 'down' : 'up'} />
                    </button>
                    {onClose && (
                        <button
                            className={styles.closeBtn}
                            onClick={(e) => { e.stopPropagation(); onClose(); }}
                            aria-label="Close browser"
                        >
                            ✕
                        </button>
                    )}
                </div>
            </div>

            {!isCollapsed && (
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

                    {snapshot.screenshot && (
                        <div
                            className={styles.screenshotContainer}
                            onClick={() => setLightboxOpen(true)}
                        >
                            <img
                                key={snapshot.screenshot.substring(0, 50)}
                                src={`data:image/png;base64,${snapshot.screenshot}`}
                                alt="Browser screenshot"
                                className={styles.screenshot}
                            />
                            {onAttachScreenshot && (
                                <button
                                    className={styles.attachButton}
                                    onClick={(e) => { e.stopPropagation(); onAttachScreenshot(snapshot.screenshot); }}
                                    title="Attach screenshot to chat"
                                    aria-label="Attach screenshot to chat"
                                >
                                    <PaperclipIcon size={24} />
                                </button>
                            )}
                        </div>
                    )}
                    {lightboxOpen && (
                        <BrowserLightbox
                            src={`data:image/png;base64,${snapshot.screenshot}`}
                            alt="Browser screenshot"
                            onClose={() => setLightboxOpen(false)}
                        />
                    )}
                </div>
            )}
        </div>
    );
}
