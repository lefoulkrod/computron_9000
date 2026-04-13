import { useState } from 'react';
import PreviewShell from './PreviewShell.jsx';
import styles from './BrowserPreview.module.css';
import PaperclipIcon from './icons/PaperclipIcon.jsx';
import BrowserIcon from './icons/BrowserIcon.jsx';
import LockIcon from './icons/LockIcon.jsx';
import Lightbox from './Lightbox.jsx';

/**
 * Browser preview component showing screenshot and URL.
 *
 * @param {Object} props
 * @param {Object} props.snapshot - Browser snapshot data
 * @param {function(string): void} [props.onAttachScreenshot] - Callback when attach button clicked
 * @param {function(): void} [props.onClose] - Callback when close button clicked
 * @param {boolean} [props.hideShell] - If true, render without PreviewShell wrapper
 * @returns {JSX.Element|null}
 */
export default function BrowserPreview({ snapshot, onAttachScreenshot, onClose, hideShell }) {
    const [lightboxOpen, setLightboxOpen] = useState(false);

    if (!snapshot) return null;

    const screenshotSrc = snapshot.screenshot
        ? `data:image/png;base64,${snapshot.screenshot}`
        : null;

    const attachBtn = onAttachScreenshot && snapshot.screenshot ? (
        <button
            className={styles.attachButton}
            onClick={(e) => { e.stopPropagation(); onAttachScreenshot(snapshot.screenshot); }}
            title="Attach screenshot to chat"
            aria-label="Attach screenshot to chat"
        >
            <PaperclipIcon size={14} />
        </button>
    ) : null;

    const content = (
        <div className={styles.content}>
            <div className={styles.urlBar}>
                <LockIcon size={12} className={styles.lockIcon} />
                <span className={styles.url} title={snapshot.url}>
                    {snapshot.url}
                </span>
                {attachBtn}
            </div>

            {snapshot.title && (
                <div className={styles.pageTitle} title={snapshot.title}>
                    {snapshot.title}
                </div>
            )}

            {screenshotSrc && (
                <div
                    className={styles.screenshotContainer}
                    onClick={() => setLightboxOpen(true)}
                >
                    <img
                        key={snapshot.screenshot.substring(0, 50)}
                        src={screenshotSrc}
                        alt="Browser screenshot"
                        className={styles.screenshot}
                    />
                </div>
            )}
            {lightboxOpen && screenshotSrc && (
                <Lightbox
                    src={screenshotSrc}
                    alt="Browser screenshot"
                    onClose={() => setLightboxOpen(false)}
                />
            )}
        </div>
    );

    if (hideShell) {
        return content;
    }

    return (
        <PreviewShell
            icon={<BrowserIcon size={16} />}
            title="Browser"
            onClose={onClose}
            expandContent={screenshotSrc ? (
                <img src={screenshotSrc} alt="Browser screenshot" className={styles.expandedImg} />
            ) : undefined}
            headerExtra={null}
        >
            {content}
        </PreviewShell>
    );
}
