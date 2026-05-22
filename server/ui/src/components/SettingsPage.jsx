import { useState } from 'react';

import IntegrationsTab from './integrations/IntegrationsTab.jsx';
import ProfilesTab from './ProfilesTab.jsx';
import ProvidersTab from './providers/ProvidersTab.jsx';
import SystemSettings from './SystemSettings.jsx';
import styles from './SettingsPage.module.css';

// Tab registry — tabs own their own data (via context / their own
// hooks), so adding a new tab is just a row here plus the component.
const TABS = [
    { id: 'profiles', label: 'Agent Profiles', Component: ProfilesTab },
    { id: 'providers', label: 'Providers', Component: ProvidersTab },
    { id: 'integrations', label: 'Integrations', Component: IntegrationsTab },
    { id: 'system', label: 'System', Component: SystemSettings },
];

export default function SettingsPage({ initialTab = 'profiles' }) {
    const [activeTab, setActiveTab] = useState(initialTab);
    const active = TABS.find((t) => t.id === activeTab) ?? TABS[0];
    const Active = active.Component;
    return (
        <div className={styles.page}>
            <nav className={styles.tabBar}>
                {TABS.map((tab) => (
                    <button
                        key={tab.id}
                        className={`${styles.tab} ${activeTab === tab.id ? styles.tabActive : ''}`}
                        onClick={() => setActiveTab(tab.id)}
                    >
                        {tab.label}
                    </button>
                ))}
            </nav>
            <div className={styles.content}>
                <Active />
            </div>
        </div>
    );
}
