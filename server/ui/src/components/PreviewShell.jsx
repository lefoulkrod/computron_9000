import { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import styles from './PreviewShell.module.css';
import ChevronIcon from './icons/ChevronIcon.jsx';

function ExpandOverlay({ children, onClose, fit }) {
    const handleKey = useCallback((e) => {
        if (e.key === 'Escape') onClose();
    }, [onClose]);

    useEffect(() => {
        document.addEventListener('keydown', handleKey);
        return () => document.removeEventListener('keydown', handleKey);
    }, [handleKey]);

    return createPortal(
        <div className={styles.overlay} onClick={onClose}>
            <div className={`${styles.overlayPanel}${fit ? ` ${styles.overlayPanelFit}` : ''}`} onClick={(e) => e.stopPropagation()}>
                <div className={styles.overlayHeader}>
                    <button
                        className={styles.overlayCloseBtn}
                        onClick={onClose}
                        aria-label="Close overlay"
                    >
                        &#10005;
                    </button>
                </div>
                <div className={styles.overlayContent}>
                    {children}
                </div>
            </div>
        </div>,
        document.body
    );
}

export default function PreviewShell({ icon, title, onClose, expandContent, expandFit, headerExtra, children }) {
    const [isCollapsed, setIsCollapsed] = useState(false);
    const [expanded, setExpanded] = useState(false);

    return (
        <div className={styles.shell}>
            <div className={styles.header} onClick={() => setIsCollapsed((c) => !c)}>
                <div className={styles.headerLeft}>
                    <span className={styles.icon}>{icon}</span>
                    <span className={styles.title} title={typeof title === 'string' ? title : undefined}>
                        {title}
                    </span>
                </div>
                <div className={styles.headerRight}>
                    {headerExtra}
                    {expandContent && (
                        <button
                            className={styles.actionBtn}
                            onClick={(e) => { e.stopPropagation(); setExpanded(true); }}
                            aria-label="Open fullscreen"
                            title="Open fullscreen"
                        >
                            &#9974;
                        </button>
                    )}
                    <button
                        className={styles.actionBtn}
                        aria-label={isCollapsed ? 'Expand' : 'Collapse'}
                    >
                        <ChevronIcon size={12} direction={isCollapsed ? 'down' : 'up'} />
                    </button>
                    {onClose && (
                        <button
                            className={styles.actionBtn}
                            onClick={(e) => { e.stopPropagation(); onClose(); }}
                            aria-label="Close"
                        >
                            &#10005;
                        </button>
                    )}
                </div>
            </div>

            {!isCollapsed && (
                <div className={styles.content}>
                    {children}
                </div>
            )}

            {expanded && expandContent && (
                <ExpandOverlay onClose={() => setExpanded(false)} fit={expandFit}>
                    {expandContent}
                </ExpandOverlay>
            )}
        </div>
    );
}

export { ExpandOverlay };
