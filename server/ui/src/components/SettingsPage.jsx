import styles from './SettingsPage.module.css';

const TABS = [
    { id: 'profiles', label: 'Agent Profiles' },
    { id: 'integrations', label: 'Integrations' },
    { id: 'system', label: 'System' },
];

export default function SettingsPage({ activeTab = 'profiles', onTabChange, children }) {
    return (
        <div className={styles.page}>
            <nav className={styles.tabBar}>
                {TABS.map(tab => (
                    <button
                        key={tab.id}
                        className={`${styles.tab} ${activeTab === tab.id ? styles.tabActive : ''}`}
                        onClick={() => onTabChange?.(tab.id)}
                    >
                        {tab.label}
                    </button>
                ))}
            </nav>
            <div className={styles.content}>
                {children}
            </div>
        </div>
    );
}
