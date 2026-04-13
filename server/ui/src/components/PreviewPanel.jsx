import styles from './PreviewPanel.module.css';
import ExpandIcon from './icons/ExpandIcon.jsx';
import RefreshIcon from './icons/RefreshIcon.jsx';

/**
 * Tab bar component for the preview panel.
 *
 * @param {Object} props
 * @param {Array<{id: string, label: string, icon: JSX.Element}>} props.tabs - Array of tab objects
 * @param {string|null} props.activeTab - Currently active tab ID
 * @param {function(string): void} props.onTabChange - Callback when tab is clicked
 * @param {function(string): void} props.onCloseTab - Callback when tab close is clicked
 * @param {function(): void} props.onFullscreen - Callback when fullscreen button is clicked
 * @param {function(): void} [props.onRefresh] - Optional callback when refresh button is clicked
 * @returns {JSX.Element}
 */
function TabBar({ tabs, activeTab, onTabChange, onCloseTab, onFullscreen, onRefresh }) {
    return (
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
            <div className={styles.tabActions}>
                {onRefresh && (
                    <button
                        className={styles.actionBtn}
                        onClick={onRefresh}
                        title="Refresh"
                        aria-label="Refresh"
                    >
                        <RefreshIcon size={14} />
                    </button>
                )}
                {onFullscreen && (
                    <button
                        className={styles.actionBtn}
                        onClick={onFullscreen}
                        title="Fullscreen"
                        aria-label="Fullscreen"
                    >
                        <ExpandIcon size={14} />
                    </button>
                )}
            </div>
        </div>
    );
}

/**
 * The unified right panel with tab bar and content area.
 *
 * @param {Object} props
 * @param {Array<{id: string, label: string, icon: JSX.Element}>} props.tabs - Array of tab objects
 * @param {string|null} props.activeTab - Currently active tab ID
 * @param {function(string): void} props.onTabChange - Callback when tab is clicked
 * @param {function(string): void} props.onCloseTab - Callback when tab close is clicked
 * @param {function(): void} props.onFullscreen - Callback when fullscreen button is clicked
 * @param {function(): void} [props.onRefresh] - Optional callback when refresh button is clicked
 * @param {React.ReactNode} props.children - The active preview content
 * @returns {JSX.Element}
 */
export default function PreviewPanel({
    tabs,
    activeTab,
    onTabChange,
    onCloseTab,
    onFullscreen,
    onRefresh,
    children,
}) {
    return (
        <div className={styles.previewPanel}>
            <TabBar
                tabs={tabs}
                activeTab={activeTab}
                onTabChange={onTabChange}
                onCloseTab={onCloseTab}
                onFullscreen={onFullscreen}
                onRefresh={onRefresh}
            />
            <div className={styles.contentArea}>
                {children}
            </div>
        </div>
    );
}
