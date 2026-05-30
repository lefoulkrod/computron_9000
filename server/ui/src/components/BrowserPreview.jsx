import { useState } from 'react';
import styles from './BrowserPreview.module.css';
import LockIcon from './icons/LockIcon.jsx';
import ExpandIcon from './icons/ExpandIcon.jsx';
import IconButton from './primitives/IconButton.jsx';

/** Extract a short host label from a URL for the thumbnail caption. */
function _hostOf(url) {
    if (!url) return '';
    try {
        return new URL(url).host.replace(/^www\./, '');
    } catch {
        return url;
    }
}

/**
 * `tabs` is an array of ``{ id, snapshot }`` for every open browser tab.
 * BrowserPreview picks one to display in the main area — the first one
 * by default, or whichever the user last clicked in the rail.  The rail
 * only renders when there's more than one tab.
 */
export default function BrowserPreview({ tabs, onFullscreen }) {
    const [selectedId, setSelectedId] = useState(tabs[0]?.id ?? null);

    const activeTab = tabs.find(t => t.id === selectedId) || tabs[0];
    if (!activeTab) return null;

    const activeSnapshot = activeTab.snapshot;
    const screenshotSrc = activeSnapshot.screenshot
        ? `data:image/png;base64,${activeSnapshot.screenshot}`
        : null;
    const showRail = tabs.length > 1;

    return (
        <div className={styles.content}>
            <div className={styles.urlBar}>
                <LockIcon size={12} className={styles.lockIcon} />
                <span className={styles.url} title={activeSnapshot.url}>
                    {activeSnapshot.url}
                </span>
                {onFullscreen && (
                    <IconButton
                        size="sm"
                        onClick={onFullscreen}
                        title="Fullscreen"
                        aria-label="Open fullscreen"
                        data-testid="browser-fullscreen"
                    >
                        <ExpandIcon size={14} />
                    </IconButton>
                )}
            </div>

            {activeSnapshot.title && (
                <div className={styles.pageTitle} title={activeSnapshot.title}>
                    {activeSnapshot.title}
                </div>
            )}

            {screenshotSrc && (
                <div
                    className={styles.screenshotContainer}
                    onClick={onFullscreen}
                >
                    <img
                        key={activeSnapshot.screenshot.substring(0, 50)}
                        src={screenshotSrc}
                        alt="Browser screenshot"
                        className={styles.screenshot}
                    />
                </div>
            )}

            {showRail && (
                <div className={styles.thumbRail} role="tablist" aria-label="Open browser tabs">
                    {tabs.map(({ id, snapshot: tabSnap }) => {
                        const thumbSrc = tabSnap.screenshot
                            ? `data:image/png;base64,${tabSnap.screenshot}`
                            : null;
                        const host = _hostOf(tabSnap.url);
                        const isActive = id === activeTab.id;
                        return (
                            <button
                                key={id}
                                type="button"
                                role="tab"
                                aria-selected={isActive}
                                title={tabSnap.title || tabSnap.url}
                                className={`${styles.thumbCard} ${isActive ? styles.thumbCardActive : ''}`}
                                onClick={() => setSelectedId(id)}
                            >
                                <div className={styles.thumbFrame}>
                                    {thumbSrc && (
                                        <img
                                            src={thumbSrc}
                                            alt=""
                                            className={styles.thumbImg}
                                        />
                                    )}
                                </div>
                                <div className={styles.thumbMeta}>{host}</div>
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
