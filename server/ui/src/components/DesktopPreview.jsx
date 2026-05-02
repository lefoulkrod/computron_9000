import { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import styles from './DesktopPreview.module.css';
import ExpandIcon from './icons/ExpandIcon.jsx';

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
                        ×
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

/**
 * Desktop preview component showing VNC view.
 *
 * @param {Object} props
 * @param {boolean} props.visible - Whether the desktop is visible
 * @param {function(): void} [props.onClose] - Callback when close button clicked (overlay mode)
 * @param {boolean} [props.overlay] - If true, render as overlay lightbox
 * @returns {JSX.Element|null}
 */
export default function DesktopPreview({ visible, onClose, overlay }) {
    const [interactive, setInteractive] = useState(false);
    const [expanded, setExpanded] = useState(false);

    if (!visible) return null;

    const toggle = () => setInteractive((v) => !v);

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
            <div className={styles.inlineControls}>
                <ControlButton interactive={interactive} onToggle={toggle} />
                <button
                    className={styles.expandBtn}
                    onClick={() => setExpanded(true)}
                    aria-label="Open fullscreen"
                    title="Open fullscreen"
                >
                    <ExpandIcon size={14} />
                </button>
            </div>
            <iframe
                key={interactive ? 'active' : 'passive'}
                className={styles.vncFrame}
                src={vncUrl}
                title="Desktop View"
                allow="clipboard-read; clipboard-write"
            />
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
