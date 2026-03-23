import { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import PreviewShell from './PreviewShell.jsx';
import styles from './DesktopPreview.module.css';

const DesktopIcon = () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
        <line x1="8" y1="21" x2="16" y2="21" />
        <line x1="12" y1="17" x2="12" y2="21" />
    </svg>
);

const MouseIcon = ({ size = 14 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 3l7.07 16.97 2.51-7.39 7.39-2.51L3 3z" />
        <path d="M13 13l6 6" />
    </svg>
);

function _buildVncUrl(interactive) {
    const base = `http://${window.location.hostname}:6080/vnc_lite.html?autoconnect=true&resize=scale&show_dot=true`;
    // noVNC reads URL params as strings — the string "false" is truthy in JS,
    // so we must omit view_only entirely for interactive mode (default is off).
    return interactive ? base : `${base}&view_only=true`;
}

function ControlButton({ interactive, onToggle, className }) {
    return (
        <button
            className={`${styles.controlBtn} ${interactive ? styles.controlBtnActive : ''} ${className || ''}`}
            onClick={(e) => { e.stopPropagation(); onToggle(); }}
            title={interactive ? 'Release control' : 'Take control'}
            aria-label={interactive ? 'Release control' : 'Take control'}
        >
            <MouseIcon size={14} />
        </button>
    );
}

function DesktopLightbox({ interactive, onToggle, onClose }) {
    const handleKey = useCallback((e) => {
        // Only close on Escape when not controlling — otherwise the keypress
        // is meant for the VNC session.
        if (e.key === 'Escape' && !interactive) onClose();
    }, [onClose, interactive]);

    useEffect(() => {
        document.addEventListener('keydown', handleKey);
        return () => document.removeEventListener('keydown', handleKey);
    }, [handleKey]);

    const vncUrl = _buildVncUrl(interactive);

    return createPortal(
        <div className={styles.lightbox} onClick={interactive ? undefined : onClose}>
            <div className={styles.lightboxPanel} onClick={(e) => e.stopPropagation()}>
                <div className={styles.lightboxHeader}>
                    <ControlButton interactive={interactive} onToggle={onToggle} />
                    <button
                        className={styles.lightboxCloseBtn}
                        onClick={onClose}
                        aria-label="Close"
                    >
                        &#10005;
                    </button>
                </div>
                <iframe
                    key={interactive ? 'active' : 'passive'}
                    className={styles.expandedFrame}
                    src={vncUrl}
                    title="Desktop View (expanded)"
                    allow="clipboard-read; clipboard-write"
                />
            </div>
        </div>,
        document.body
    );
}

export default function DesktopPreview({ visible, onClose, overlay }) {
    const [interactive, setInteractive] = useState(false);
    const [expanded, setExpanded] = useState(false);

    if (!visible) return null;

    const toggle = () => setInteractive((v) => !v);

    // Overlay mode: render lightbox directly (used from header button in network/agent views)
    if (overlay) {
        return (
            <DesktopLightbox
                interactive={interactive}
                onToggle={toggle}
                onClose={onClose}
            />
        );
    }

    const vncUrl = _buildVncUrl(interactive);

    return (
        <>
            <PreviewShell
                icon={<DesktopIcon />}
                title={interactive ? 'Desktop (controlling)' : 'Desktop'}
                onClose={onClose}
                headerExtra={
                    <>
                        <ControlButton interactive={interactive} onToggle={toggle} />
                        <button
                            className={styles.expandBtn}
                            onClick={(e) => { e.stopPropagation(); setExpanded(true); }}
                            aria-label="Open fullscreen"
                            title="Open fullscreen"
                        >
                            &#9974;
                        </button>
                    </>
                }
            >
                <iframe
                    key={interactive ? 'active' : 'passive'}
                    className={styles.vncFrame}
                    src={vncUrl}
                    title="Desktop View"
                    allow="clipboard-read; clipboard-write"
                />
            </PreviewShell>

            {expanded && (
                <DesktopLightbox
                    interactive={interactive}
                    onToggle={toggle}
                    onClose={() => setExpanded(false)}
                />
            )}
        </>
    );
}
