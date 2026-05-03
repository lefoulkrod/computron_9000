import FullscreenPreview from './FullscreenPreview.jsx';
import styles from './BrowserFullscreen.module.css';

export default function BrowserFullscreen({ snapshot, onClose }) {
    if (!snapshot) return null;

    const screenshotSrc = snapshot.screenshot
        ? `data:image/png;base64,${snapshot.screenshot}`
        : null;

    return (
        <FullscreenPreview
            title={snapshot.url || 'Browser'}
            onClose={onClose}
        >
            {screenshotSrc && (
                <div className={styles.imageContainer}>
                    <img
                        src={screenshotSrc}
                        alt="Browser screenshot"
                        className={styles.image}
                    />
                </div>
            )}
        </FullscreenPreview>
    );
}
