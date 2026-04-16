import styles from './Message.module.css';
import { canPreviewFile } from '../utils/fileTypes.js';
import FileIcon from './icons/FileIcon.jsx';
import ImageIcon from './icons/ImageIcon.jsx';
import SourceIcon from './icons/SourceIcon.jsx';
import DownloadIcon from './icons/DownloadIcon.jsx';
import EyeIcon from './icons/EyeIcon.jsx';

function FileOutputIcon({ contentType, filename }) {
    if (contentType?.startsWith('image/') || filename?.match(/\.(jpg|jpeg|png|gif|webp|svg)$/i)) {
        return <ImageIcon size={16} />;
    }
    if (contentType?.startsWith('text/') || filename?.match(/\.(js|jsx|ts|tsx|py|java|cpp|c|h|go|rs|rb|php|html|css|json|xml|yaml|yml|md|txt)$/i)) {
        return <SourceIcon size={16} />;
    }
    return <FileIcon size={16} />;
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
                <span className={styles.fileOutputIcon}>
                    <FileOutputIcon contentType={content_type} filename={filename} />
                </span>
                <div className={styles.fileOutputInfo}>
                    <span className={styles.fileOutputName}>{filename}</span>
                    <span className={styles.fileOutputMime}>{content_type}</span>
                </div>
                <div className={styles.fileOutputBtns}>
                    {previewable && onPreview && (
                        <button
                            className={styles.fileOutputBtn}
                            onClick={(e) => { e.stopPropagation(); onPreview(item); }}
                            data-testid="file-preview-btn"
                        >
                            <EyeIcon size={12} />
                            Preview
                        </button>
                    )}
                    <button className={styles.fileOutputBtn} onClick={handleDownload} data-testid="file-download-btn">
                        <DownloadIcon size={12} />
                        Download
                    </button>
                </div>
            </div>
        </div>
    );
}
