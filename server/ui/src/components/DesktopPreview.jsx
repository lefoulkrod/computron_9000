import PreviewShell from './PreviewShell.jsx';
import styles from './DesktopPreview.module.css';

const DesktopIcon = () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
        <line x1="8" y1="21" x2="16" y2="21" />
        <line x1="12" y1="17" x2="12" y2="21" />
    </svg>
);

export default function DesktopPreview({ visible, onClose }) {
    if (!visible) return null;

    const vncUrl = `http://${window.location.hostname}:6080/vnc_lite.html?autoconnect=true&resize=scale&view_only=true&show_dot=true`;

    return (
        <PreviewShell
            icon={<DesktopIcon />}
            title="Desktop"
            onClose={onClose}
            expandFit
            expandContent={
                <iframe
                    className={styles.expandedFrame}
                    src={vncUrl}
                    title="Desktop View (expanded)"
                    allow="clipboard-read; clipboard-write"
                />
            }
        >
            <iframe
                className={styles.vncFrame}
                src={vncUrl}
                title="Desktop View"
                allow="clipboard-read; clipboard-write"
            />
        </PreviewShell>
    );
}
