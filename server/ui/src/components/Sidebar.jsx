import React, { useCallback, useState } from 'react';
import AudioIndicator from './AudioIndicator.jsx';
import RecentConversations from './RecentConversations.jsx';
import styles from './Sidebar.module.css';

const COLLAPSE_KEY = 'computron_sidebar_collapsed';

// Panels reachable from the nav. Settings + theme live in the footer;
// conversations live inline in the recent list below the nav. The agent
// network view is opened from the chat title-bar pill, not a nav item.
// Memory and Custom Tools live under Settings, not in the nav.
const NAV = [
    { id: 'goals', icon: 'bi-bullseye', label: 'Goals' },
];

function _readCollapsed() {
    try {
        return localStorage.getItem(COLLAPSE_KEY) === '1';
    } catch {
        return false;
    }
}

/**
 * Left navigation rail. Collapses to an icon-only strip or expands to
 * show labels, the COMPUTRON wordmark, and a primary "New chat" button.
 * The collapsed/expanded choice is persisted to localStorage.
 */
export default function Sidebar({
    activePanel,
    onPanelToggle,
    dark,
    onToggleTheme,
    onNewConversation,
    audio,
    muted,
    onToggleMute,
    onAudioEnded,
    desktopEnabled,
    onOpenDesktop,
    onLoadConversation,
    activeConversationId,
    conversationsRefresh = 0,
}) {
    const [collapsed, setCollapsed] = useState(_readCollapsed);

    const toggleCollapsed = useCallback(() => {
        setCollapsed((c) => {
            const next = !c;
            try {
                localStorage.setItem(COLLAPSE_KEY, next ? '1' : '0');
            } catch {
                // localStorage unavailable — collapse still works for the session.
            }
            return next;
        });
    }, []);

    const settingsActive = activePanel === 'settings';

    return (
        <aside
            className={`${styles.sidebar} ${collapsed ? styles.collapsed : styles.expanded}`}
            data-testid="sidebar"
            data-collapsed={collapsed}
        >
            <div className={styles.brand}>
                {!collapsed && <span className={styles.wordmark}>COMPUTRON</span>}
                <button
                    className={styles.iconBtn}
                    onClick={toggleCollapsed}
                    title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
                    aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
                    data-testid="sidebar-toggle"
                >
                    <i className={`bi ${collapsed ? 'bi-layout-sidebar' : 'bi-layout-sidebar-inset'}`} />
                </button>
            </div>

            <div className={styles.primary}>
                <button
                    className={styles.newChat}
                    onClick={onNewConversation}
                    title="New chat"
                    aria-label="New chat"
                    data-testid="sidebar-new-chat"
                >
                    <span className={styles.newChatIcon}>
                        <i className="bi bi-plus-lg" />
                    </span>
                    {!collapsed && <span>New chat</span>}
                </button>
            </div>

            <nav className={styles.nav}>
                {NAV.map((panel) => {
                    const active = activePanel === panel.id;
                    return (
                        <button
                            key={panel.id}
                            className={`${styles.navItem} ${active ? styles.active : ''}`}
                            onClick={() => onPanelToggle(active ? null : panel.id)}
                            title={panel.label}
                            aria-label={panel.label}
                            data-testid={`sidebar-nav-${panel.id}`}
                        >
                            <i className={`bi ${panel.icon}`} />
                            {!collapsed && <span className={styles.navLabel}>{panel.label}</span>}
                        </button>
                    );
                })}
            </nav>

            {collapsed ? (
                <div className={styles.grow} />
            ) : (
                <RecentConversations
                    onLoadConversation={onLoadConversation}
                    activeConversationId={activeConversationId}
                    refreshSignal={conversationsRefresh}
                />
            )}

            <div className={styles.footer}>
                <button
                    className={`${styles.iconBtn} ${!dark ? styles.themeOn : ''}`}
                    onClick={onToggleTheme}
                    title={dark ? 'Switch to light theme' : 'Switch to dark theme'}
                    aria-label="Toggle theme"
                    data-testid="sidebar-theme-toggle"
                >
                    <i className="bi bi-sun" />
                </button>
                <div className={styles.footerSpacer} />
                <AudioIndicator
                    audio={audio}
                    muted={muted}
                    onToggleMute={onToggleMute}
                    onEnded={onAudioEnded}
                />
                {desktopEnabled && (
                    <button
                        className={styles.iconBtn}
                        onClick={onOpenDesktop}
                        title="Open desktop"
                        aria-label="Open desktop"
                        data-testid="sidebar-desktop"
                    >
                        <i className="bi bi-display" />
                    </button>
                )}
                <button
                    className={`${styles.iconBtn} ${settingsActive ? styles.active : ''}`}
                    onClick={() => onPanelToggle(settingsActive ? null : 'settings')}
                    title="Settings"
                    aria-label="Settings"
                    data-testid="sidebar-settings"
                >
                    <i className="bi bi-gear" />
                </button>
            </div>
        </aside>
    );
}
