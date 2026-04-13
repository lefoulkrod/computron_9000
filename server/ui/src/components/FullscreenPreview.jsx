import { useState, useMemo, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import styles from './FullscreenPreview.module.css';
import ArrowLeftIcon from './icons/ArrowLeftIcon.jsx';
import DownloadIcon from './icons/DownloadIcon.jsx';
import SourceIcon from './icons/SourceIcon.jsx';
import EyeIcon from './icons/EyeIcon.jsx';

/**
 * Decodes base64 content to text.
 *
 * @param {string} b64 - Base64 encoded string
 * @returns {string} Decoded text
 */
function decodeText(b64) {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    return new TextDecoder().decode(bytes);
}

/**
 * Checks if the file can be previewed (markdown or HTML).
 *
 * @param {string} contentType - MIME type
 * @param {string} filename - File name
 * @returns {boolean}
 */
function canPreview(contentType, filename) {
    if (contentType === 'text/markdown' || contentType === 'text/x-markdown') return true;
    if (contentType === 'text/html') return true;
    if (filename?.endsWith('.md') || filename?.endsWith('.mdx')) return true;
    if (filename?.endsWith('.html') || filename?.endsWith('.htm')) return true;
    return false;
}

/**
 * Checks if the file is an image.
 *
 * @param {string} contentType - MIME type
 * @param {string} filename - File name
 * @returns {boolean}
 */
function isImage(contentType, filename) {
    if (contentType?.startsWith('image/')) return true;
    if (filename?.match(/\.(jpg|jpeg|png|gif|webp|svg)$/i)) return true;
    return false;
}

/**
 * Full viewport takeover for file previews (NOT a lightbox overlay).
 *
 * @param {Object} props
 * @param {Object} props.item - File item with filename, content_type, content, path
 * @param {function(): void} props.onClose - Callback to close fullscreen view
 * @returns {JSX.Element}
 */
export default function FullscreenPreview({ item, onClose }) {
    const [fetchedText, setFetchedText] = useState(null);
    const [viewMode, setViewMode] = useState(() => {
        // Default to 'preview' for markdown/HTML, 'source' for everything else
        return canPreview(item?.content_type, item?.filename) ? 'preview' : 'source';
    });

    const { filename, content_type, content, path } = item;

    const itemKey = path || content;
    useEffect(() => {
        setFetchedText(null);
        // Reset view mode when item changes
        setViewMode(canPreview(content_type, filename) ? 'preview' : 'source');
    }, [itemKey, content_type, filename]);

    const text = useMemo(() => {
        if (content) return decodeText(content);
        return fetchedText;
    }, [content, fetchedText]);

    useEffect(() => {
        if (content || !path) return;
        let cancelled = false;
        fetch(path).then(r => r.text()).then(t => {
            if (!cancelled) setFetchedText(t);
        });
        return () => { cancelled = true; };
    }, [content, path]);

    const isHtml = content_type === 'text/html';
    const isMarkdown =
        content_type === 'text/markdown' ||
        content_type === 'text/x-markdown' ||
        (!isHtml && filename && (filename.endsWith('.md') || filename.endsWith('.mdx')));
    const showToggle = isHtml || isMarkdown;
    const isImageFile = isImage(content_type, filename);

    const iframeSrc = useMemo(() => {
        if (isHtml && path) return path;
        if (isHtml && text) {
            const blob = new Blob([text], { type: 'text/html' });
            return URL.createObjectURL(blob);
        }
        return null;
    }, [isHtml, path, text]);

    useEffect(() => {
        return () => {
            if (iframeSrc && iframeSrc.startsWith('blob:')) URL.revokeObjectURL(iframeSrc);
        };
    }, [iframeSrc]);

    // Escape key closes the fullscreen view
    const handleKeyDown = useCallback((e) => {
        if (e.key === 'Escape') {
            onClose();
        }
    }, [onClose]);

    useEffect(() => {
        document.addEventListener('keydown', handleKeyDown);
        return () => document.removeEventListener('keydown', handleKeyDown);
    }, [handleKeyDown]);

    const handleDownload = () => {
        const link = document.createElement('a');
        if (text) {
            const blob = new Blob([text], { type: content_type || 'text/plain' });
            link.href = URL.createObjectURL(blob);
        } else if (path) {
            link.href = path;
        }
        link.download = filename || 'file';
        link.click();
    };

    return (
        <div className={styles.fullscreenPreview}>
            {/* Header bar */}
            <div className={styles.header}>
                <div className={styles.headerLeft}>
                    <button
                        className={styles.backBtn}
                        onClick={onClose}
                        title="Back"
                        aria-label="Back to preview panel"
                    >
                        <ArrowLeftIcon size={14} />
                        Back
                    </button>
                </div>

                <div className={styles.headerCenter}>
                    <span className={styles.filename} title={filename}>
                        {filename || 'File'}
                    </span>
                </div>

                <div className={styles.headerRight}>
                    {showToggle && (
                        <div className={styles.toggle}>
                            <button
                                className={`${styles.toggleBtn} ${viewMode === 'source' ? styles.toggleBtnActive : ''}`}
                                onClick={() => setViewMode('source')}
                            >
                                <SourceIcon size={12} />
                                Source
                            </button>
                            <button
                                className={`${styles.toggleBtn} ${viewMode === 'preview' ? styles.toggleBtnActive : ''}`}
                                onClick={() => setViewMode('preview')}
                            >
                                <EyeIcon size={12} />
                                Preview
                            </button>
                        </div>
                    )}
                    <button
                        className={styles.headerBtn}
                        onClick={handleDownload}
                        title="Download"
                        aria-label="Download file"
                    >
                        <DownloadIcon size={14} />
                    </button>
                </div>
            </div>

            {/* Content area */}
            <div className={styles.content}>
                {viewMode === 'source' && (
                    <pre className={styles.sourceCode}>{text || 'Loading...'}</pre>
                )}
                {viewMode === 'preview' && isMarkdown && text && (
                    <div className={styles.markdownContent}>
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
                    </div>
                )}
                {viewMode === 'preview' && isMarkdown && !text && (
                    <div className={styles.statusText}>Loading...</div>
                )}
                {viewMode === 'preview' && isHtml && iframeSrc && (
                    <iframe
                        className={styles.htmlFrame}
                        src={iframeSrc}
                        title={filename}
                        sandbox="allow-scripts allow-same-origin"
                    />
                )}
                {viewMode === 'preview' && isHtml && !iframeSrc && (
                    <div className={styles.statusText}>Loading...</div>
                )}
                {viewMode === 'preview' && isImageFile && (
                    <div className={styles.imageContainer}>
                        {content && (
                            <img
                                src={`data:${content_type};base64,${content}`}
                                alt={filename}
                                className={styles.image}
                            />
                        )}
                        {path && !content && (
                            <img src={path} alt={filename} className={styles.image} />
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
