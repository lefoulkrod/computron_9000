import { useState } from 'react';
import styles from './DesktopView.module.css';
import ChevronIcon from './icons/ChevronIcon.jsx';

export default function DesktopView({ visible, onClose }) {
    const [isCollapsed, setIsCollapsed] = useState(false);

    if (!visible) return null;

    // noVNC web client is served by websockify inside the container.
    // The iframe connects directly to the VNC websocket.
    const vncUrl = `http://${window.location.hostname}:6080/vnc_lite.html?autoconnect=true&resize=scale&view_only=true`;

    const toggleCollapse = () => setIsCollapsed((prev) => !prev);

    return (
        <div className={styles.desktopView}>
            <div className={styles.header} onClick={toggleCollapse}>
                <div className={styles.headerLeft}>
                    <svg className={styles.desktopIcon} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
                        <line x1="8" y1="21" x2="16" y2="21" />
                        <line x1="12" y1="17" x2="12" y2="21" />
                    </svg>
                    <span className={styles.title}>Desktop</span>
                </div>
                <div className={styles.headerRight}>
                    <button className={styles.collapseBtn} aria-label={isCollapsed ? 'Expand' : 'Collapse'}>
                        <ChevronIcon size={12} direction={isCollapsed ? 'down' : 'up'} />
                    </button>
                    {onClose && (
                        <button
                            className={styles.closeBtn}
                            onClick={(e) => { e.stopPropagation(); onClose(); }}
                            aria-label="Close desktop"
                        >
                            &#10005;
                        </button>
                    )}
                </div>
            </div>

            {!isCollapsed && (
                <div className={styles.content}>
                    <iframe
                        className={styles.vncFrame}
                        src={vncUrl}
                        title="Desktop View"
                        allow="clipboard-read; clipboard-write"
                    />
                </div>
            )}
        </div>
    );
}
