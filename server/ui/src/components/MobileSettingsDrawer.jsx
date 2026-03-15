import React from 'react';
import ModelSettingsPanel from './ModelSettingsPanel.jsx';
import SessionsPanel from './SessionsPanel.jsx';
import styles from './MobileSettingsDrawer.module.css';

export default function MobileSettingsDrawer({ open, onClose, modelSettings, isStreaming, onLoadSession }) {
    return (
        <>
            <div
                className={`${styles.backdrop} ${open ? styles.open : ''}`}
                onClick={onClose}
            />
            <div className={`${styles.drawer} ${open ? styles.open : ''}`}>
                <div className={styles.drawerHeader}>
                    <span className={styles.drawerTitle}>Settings</span>
                    <button
                        className={styles.closeButton}
                        onClick={onClose}
                        aria-label="Close settings"
                    >
                        ×
                    </button>
                </div>
                <ModelSettingsPanel settings={modelSettings} disabled={isStreaming} />
                <SessionsPanel onLoadSession={onLoadSession} />
            </div>
        </>
    );
}
