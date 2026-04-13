import styles from './PreviewPanel.module.css';

/**
 * The unified right panel with tab bar and content area.
 */
export default function PreviewPanel({
    tabs,
    activeTab,
    onTabChange,
    onCloseTab,
    children,
}) {
    return (
        <div className={styles.previewPanel}>
            <div className={styles.tabBar}>
                <div className={styles.tabList}>
                    {tabs.map((tab) => {
                        const isActive = tab.id === activeTab;
                        return (
                            <button
                                key={tab.id}
                                className={`${styles.tab} ${isActive ? styles.tabActive : ''}`}
                                onClick={() => onTabChange(tab.id)}
                                title={tab.label}
                            >
                                <span className={styles.tabIcon}>{tab.icon}</span>
                                <span className={styles.tabLabel}>{tab.label}</span>
                                <span
                                    className={styles.tabClose}
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        onCloseTab(tab.id);
                                    }}
                                    title="Close tab"
                                    aria-label={`Close ${tab.label} tab`}
                                >
                                    ×
                                </span>
                            </button>
                        );
                    })}
                </div>
            </div>
            <div className={styles.contentArea}>
                {children}
            </div>
        </div>
    );
}
