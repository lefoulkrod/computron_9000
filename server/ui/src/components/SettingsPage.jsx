import { useMemo, useState } from 'react';

import { useAppData } from '../contexts/AppData.jsx';
import CustomToolsTab from './CustomToolsTab.jsx';
import IntegrationsTab from './integrations/IntegrationsTab.jsx';
import MemoryTab from './MemoryTab.jsx';
import ProfilesTab from './ProfilesTab.jsx';
import ProvidersTab from './providers/ProvidersTab.jsx';
import SystemSettings from './SystemSettings.jsx';
import styles from './SettingsPage.module.css';

// Tab registry — tabs own their own data (via context / their own
// hooks), so adding a new tab is just a row here plus the component.
// `feature` gates visibility on a features.* flag.
const ALL_TABS = [
    { id: 'profiles', label: 'Agent Profiles', Component: ProfilesTab },
    { id: 'providers', label: 'Providers', Component: ProvidersTab },
    { id: 'integrations', label: 'Integrations', Component: IntegrationsTab },
    { id: 'memory', label: 'Memory', Component: MemoryTab },
    { id: 'tools', label: 'Custom Tools', Component: CustomToolsTab, feature: 'custom_tools' },
    { id: 'system', label: 'System', Component: SystemSettings },
];

export default function SettingsPage({
    initialTab = 'profiles',
    memoryRefreshSignal = 0,
    toolsRefreshSignal = 0,
}) {
    const { features } = useAppData();
    const tabs = useMemo(
        () => ALL_TABS.filter((t) => !t.feature || features[t.feature]),
        [features],
    );
    const [activeTab, setActiveTab] = useState(initialTab);
    const active = tabs.find((t) => t.id === activeTab) ?? tabs[0];
    const Active = active.Component;
    // Only the Memory and Custom Tools tabs need the refresh signal —
    // bumped by agent-side remember/forget and tool_created events. Other
    // tabs ignore the prop.
    const tabProps = active.id === 'memory'
        ? { refreshSignal: memoryRefreshSignal }
        : active.id === 'tools'
            ? { refreshSignal: toolsRefreshSignal }
            : {};
    return (
        <div className={styles.page}>
            <nav className={styles.tabBar}>
                {tabs.map((tab) => (
                    <button
                        key={tab.id}
                        className={`${styles.tab} ${active.id === tab.id ? styles.tabActive : ''}`}
                        onClick={() => setActiveTab(tab.id)}
                    >
                        {tab.label}
                    </button>
                ))}
            </nav>
            <div className={styles.content}>
                <Active {...tabProps} />
            </div>
        </div>
    );
}
