import React from 'react';
import styles from './Sidebar.module.css';

const PANELS = [
    { id: 'agents', icon: 'bi-diagram-3', label: 'Agents' },
    { id: 'goals', icon: 'bi-bullseye', label: 'Goals' },
    { id: 'memory', icon: 'bi-database', label: 'Memory' },
    { id: 'sep' },
    { id: 'conversations', icon: 'bi-clock-history', label: 'Conversations' },
    { id: 'tools', icon: 'bi-wrench', label: 'Tools' },
    { id: 'sep2' },
    { id: 'settings', icon: 'bi-gear', label: 'Settings' },
];

export default function Sidebar({ activePanel, onPanelToggle, hiddenPanels = [] }) {
    return (
        <div className={styles.sidebar}>
            {PANELS.filter((p) => !hiddenPanels.includes(p.id)).map((panel) => {
                if (panel.id === 'sep') {
                    return <div key={panel.id} className={styles.sep} />;
                }
                if (panel.id === 'sep2') {
                    return <div key={panel.id} className={styles.spacer} />;
                }
                const isActive = activePanel === panel.id;
                return (
                    <button
                        key={panel.id}
                        className={`${styles.btn} ${isActive ? styles.active : ''}`}
                        title={panel.label}
                        aria-label={panel.label}
                        onClick={() => onPanelToggle(isActive ? null : panel.id)}
                    >
                        <i className={panel.icon} />
                    </button>
                );
            })}
        </div>
    );
}
