import styles from './Message.module.css';
import { canPreviewFile } from '../utils/fileTypes.js';

function fileIcon(contentType) {
    if (!contentType) return '📄';
    if (contentType.startsWith('image/')) return '🖼️';
    if (contentType.startsWith('audio/')) return '🎵';
    if (contentType.startsWith('video/')) return '🎬';
    if (contentType === 'application/pdf') return '📕';
    if (contentType.startsWith('text/csv') || contentType === 'text/tab-separated-values') return '📊';
    if (contentType.startsWith('text/')) return '📄';
    if (contentType.includes('json')) return '📋';
    if (contentType.includes('zip') || contentType.includes('tar') || contentType.includes('gzip')) return '📦';
    return '📎';
}

export default function FileOutput({ item, onPreview }) {
    const { filename, content_type, content, path } = item;
    const previewable = canPreviewFile(content_type, filename);

    const handleDownload = (e) => {
        e.stopPropagation();
        if (path) {
            const a = document.createElement('a');
            a.href = path;
            a.download = filename;
            a.click();
            return;
        }
        const byteChars = atob(content);
        const bytes = new Uint8Array(byteChars.length);
        for (let i = 0; i < byteChars.length; i++) bytes[i] = byteChars.charCodeAt(i);
        const blob = new Blob([bytes], { type: content_type || 'application/octet-stream' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 100);
    };

    const handleClick = () => {
        if (previewable && onPreview) {
            onPreview(item);
        } else {
            handleDownload(new Event('click'));
        }
    };

    return (
        <div className={styles.fileOutput} onClick={handleClick} style={{ cursor: 'pointer' }}>
            <div className={styles.fileOutputHeader}>
                <span className={styles.fileOutputIcon}>{fileIcon(content_type)}</span>
                <div className={styles.fileOutputInfo}>
                    <span className={styles.fileOutputName}>{filename}</span>
                    <span className={styles.fileOutputMime}>{content_type}</span>
                </div>
                <div className={styles.fileOutputBtns}>
                    {previewable && onPreview && (
                        <button
                            className={styles.fileOutputBtn}
                            onClick={(e) => { e.stopPropagation(); onPreview(item); }}
                        >
                            Preview
                        </button>
                    )}
                    <button className={styles.fileOutputBtn} onClick={handleDownload}>
                        Download
                    </button>
                </div>
            </div>
        </div>
    );
}
