import { useState, useMemo, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import styles from './FilePreviewInline.module.css';
import FileIcon from './icons/FileIcon.jsx';
import DownloadIcon from './icons/DownloadIcon.jsx';
import ExpandIcon from './icons/ExpandIcon.jsx';
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
 * Gets the appropriate file icon based on content type.
 *
 * @param {string} contentType - MIME type
 * @param {string} filename - File name
 * @returns {JSX.Element}
 */
function getFileIcon(contentType, filename) {
    // Image files
    if (contentType?.startsWith('image/') || filename?.match(/\.(jpg|jpeg|png|gif|webp|svg)$/i)) {
        return (
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="1" y="2" width="14" height="12" rx="1" stroke="currentColor" strokeWidth="1.2"/>
                <circle cx="5" cy="6" r="1.5" fill="currentColor"/>
                <path d="M1 12l4-4 3 3 3-3 4 4" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/>
            </svg>
        );
    }
    // Code/text files
    if (contentType?.startsWith('text/') || filename?.match(/\.(js|jsx|ts|tsx|py|java|cpp|c|h|go|rs|rb|php|html|css|json|xml|yaml|yml|md|txt)$/i)) {
        return <SourceIcon size={14} />;
    }
    return <FileIcon size={14} />;
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
 * Inline file preview that renders inside PreviewPanel.
 * Replaces the old FilePreview lightbox.
 *
 * @param {Object} props
 * @param {Object} props.item - File item with filename, content_type, content, path
 * @param {function(): void} props.onFullscreen - Callback to open fullscreen view
 * @returns {JSX.Element}
 */
export default function FilePreviewInline({ item, onFullscreen }) {
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

    const fileIcon = getFileIcon(content_type, filename);

    return (
        <div className={styles.filePreview}>
            {/* File toolbar */}
            <div className={styles.toolbar}>
                <div className={styles.toolbarLeft}>
                    <div className={styles.filePill}>
                        <span className={styles.fileIcon}>{fileIcon}</span>
                        <span className={styles.fileName} title={filename}>
                            {filename || 'File'}
                        </span>
                    </div>
                </div>

                <div className={styles.toolbarCenter}>
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
                    {!showToggle && (
                        <div className={styles.toggle}>
                            <button className={`${styles.toggleBtn} ${styles.toggleBtnActive}`}>
                                <SourceIcon size={12} />
                                Source
                            </button>
                        </div>
                    )}
                </div>

                <div className={styles.toolbarRight}>
                    <button
                        className={styles.toolbarBtn}
                        onClick={handleDownload}
                        title="Download"
                        aria-label="Download file"
                    >
                        <DownloadIcon size={14} />
                    </button>
                    <button
                        className={styles.toolbarBtn}
                        onClick={onFullscreen}
                        title="Fullscreen"
                        aria-label="Open fullscreen"
                    >
                        <ExpandIcon size={14} />
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
