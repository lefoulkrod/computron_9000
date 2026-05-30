import { useState, useEffect } from 'react';
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
 *
 * When the consumer has just a single tab, passing ``tabs=[{ id, snapshot }]``
 * works the same as passing the legacy ``snapshot`` prop alone.
 */
export default function BrowserPreview({ snapshot, tabs, onFullscreen }) {
    // Normalize to a tabs array; legacy callers pass only `snapshot`.
    const tabList = Array.isArray(tabs) && tabs.length > 0
        ? tabs
        : (snapshot ? [{ id: 'only', snapshot }] : []);

    const [selectedId, setSelectedId] = useState(tabList[0]?.id ?? null);

    // If the currently-selected tab disappears (e.g. agent closed it),
    // fall back to the first available tab.  Initial first-tab pick is
    // handled by useState default.
    useEffect(() => {
        if (!tabList.some(t => t.id === selectedId)) {
            setSelectedId(tabList[0]?.id ?? null);
        }
    }, [tabList, selectedId]);

    const activeTab = tabList.find(t => t.id === selectedId) || tabList[0];
    if (!activeTab) return null;

    const activeSnapshot = activeTab.snapshot;
    const screenshotSrc = activeSnapshot.screenshot
        ? `data:image/png;base64,${activeSnapshot.screenshot}`
        : null;
    const showRail = tabList.length > 1;

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
                    {tabList.map(({ id, snapshot: tabSnap }) => {
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
