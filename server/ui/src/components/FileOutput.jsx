import { useState } from 'react';
import styles from './Message.module.css';
import Lightbox from './Lightbox.jsx';

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
    const isImage = content_type && content_type.startsWith('image/');
    const isAudio = content_type && content_type.startsWith('audio/');
    const isVideo = content_type && content_type.startsWith('video/');
    const isPreviewable =
        content_type === 'text/html' ||
        content_type === 'text/markdown' ||
        content_type === 'text/x-markdown' ||
        (content_type === 'text/plain' && filename && (filename.endsWith('.md') || filename.endsWith('.mdx')));
    const [previewOpen, setPreviewOpen] = useState(false);
    const [lightboxOpen, setLightboxOpen] = useState(false);

    const handleDownload = () => {
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
        URL.revokeObjectURL(url);
    };

    const src = path || `data:${content_type};base64,${content}`;

    return (
        <div className={styles.fileOutput}>
            <div className={styles.fileOutputHeader}>
                <span className={styles.fileOutputIcon}>{fileIcon(content_type)}</span>
                <div className={styles.fileOutputInfo}>
                    <span className={styles.fileOutputName}>{filename}</span>
                    <span className={styles.fileOutputMime}>{content_type}</span>
                </div>
                <div className={styles.fileOutputBtns}>
                    {isImage && (
                        <button
                            className={`${styles.fileOutputBtn} ${previewOpen ? styles.fileOutputBtnActive : ''}`}
                            onClick={() => setPreviewOpen(o => !o)}
                        >
                            {previewOpen ? 'Hide' : 'Preview'}
                        </button>
                    )}
                    {isPreviewable && onPreview && (
                        <button
                            className={styles.fileOutputBtn}
                            onClick={() => onPreview(item)}
                        >
                            Preview
                        </button>
                    )}
                    <button className={styles.fileOutputBtn} onClick={handleDownload}>Download</button>
                </div>
            </div>
            {isAudio && (
                <>
                    <div className={styles.fileOutputDivider} />
                    <audio className={styles.audioPlayer} controls src={src} />
                </>
            )}
            {isVideo && (
                <>
                    <div className={styles.fileOutputDivider} />
                    <video className={styles.videoPlayer} controls src={src} />
                </>
            )}
            {previewOpen && isImage && (
                <div className={styles.fileOutputImages}>
                    <img
                        src={src}
                        alt={filename}
                        className={styles.fileOutputThumb}
                        onClick={() => setLightboxOpen(true)}
                    />
                </div>
            )}
            {lightboxOpen && <Lightbox src={src} alt={filename} onClose={() => setLightboxOpen(false)} />}
        </div>
    );
}
