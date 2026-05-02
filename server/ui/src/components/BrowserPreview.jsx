import styles from './BrowserPreview.module.css';
import LockIcon from './icons/LockIcon.jsx';
import ExpandIcon from './icons/ExpandIcon.jsx';
import IconButton from './primitives/IconButton.jsx';

export default function BrowserPreview({ snapshot, onFullscreen }) {
    if (!snapshot) return null;

    const screenshotSrc = snapshot.screenshot
        ? `data:image/png;base64,${snapshot.screenshot}`
        : null;

    return (
        <div className={styles.content}>
            <div className={styles.urlBar}>
                <LockIcon size={12} className={styles.lockIcon} />
                <span className={styles.url} title={snapshot.url}>
                    {snapshot.url}
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

            {snapshot.title && (
                <div className={styles.pageTitle} title={snapshot.title}>
                    {snapshot.title}
                </div>
            )}

            {screenshotSrc && (
                <div
                    className={styles.screenshotContainer}
                    onClick={onFullscreen}
                >
                    <img
                        key={snapshot.screenshot.substring(0, 50)}
                        src={screenshotSrc}
                        alt="Browser screenshot"
                        className={styles.screenshot}
                    />
                </div>
            )}
        </div>
    );
}
