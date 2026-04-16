import React, { useState } from 'react';
import GoalsIcon from './goals/GoalsIcon.jsx';
import styles from './Sidebar.module.css';

const PANELS = [
    { id: 'agents', icon: 'M12 5a3 3 0 100-6 3 3 0 000 6zM5 19a3 3 0 100-6 3 3 0 000 6zM19 19a3 3 0 100-6 3 3 0 000 6z', lines: 'M12 8L5 16M12 8l7 8', label: 'Agents' },
    { id: 'goals', component: GoalsIcon, label: 'Goals' },
    { id: 'memory', path: 'M12 2a7 7 0 017 7c0 5-7 13-7 13S5 14 5 9a7 7 0 017-7z', icon: 'M12 9a2.5 2.5 0 100-5 2.5 2.5 0 000 5z', label: 'Memory' },
    { id: 'sep' },
    { id: 'conversations', path: 'M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z', label: 'Conversations' },
    { id: 'tools', path: 'M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z', label: 'Tools' },
    { id: 'sep2' },
    { id: 'settings', icon: 'M12 15a3 3 0 100-6 3 3 0 000 6z', path: 'M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z', label: 'Settings' },
];

function SidebarIcon({ path, icon, lines }) {
    return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            {path && <path d={path} />}
            {icon && <path d={icon} />}
            {lines && lines.split('M').filter(Boolean).map((l, i) => (
                <path key={i} d={`M${l}`} />
            ))}
        </svg>
    );
}

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
                        className={`${styles.icon} ${isActive ? styles.active : ''}`}
                        title={panel.label}
                        aria-label={panel.label}
                        onClick={() => onPanelToggle(isActive ? null : panel.id)}
                    >
                        {panel.component ? <panel.component /> : <SidebarIcon path={panel.path} icon={panel.icon} lines={panel.lines} />}
                    </button>
                );
            })}
        </div>
    );
}
