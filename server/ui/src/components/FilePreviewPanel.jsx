import { useState, useMemo, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import styles from './FilePreviewPanel.module.css';
import ChevronIcon from './icons/ChevronIcon.jsx';
import LockIcon from './icons/LockIcon.jsx';

function decodeText(b64) {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    return new TextDecoder().decode(bytes);
}

function FilePreviewOverlay({ iframeSrc, text, isHtml, isMarkdown, filename, path, onClose }) {
    const handleKey = useCallback((e) => {
        if (e.key === 'Escape') onClose();
    }, [onClose]);

    useEffect(() => {
        document.addEventListener('keydown', handleKey);
        return () => document.removeEventListener('keydown', handleKey);
    }, [handleKey]);

    const displayUrl = path || filename;

    return createPortal(
        <div className={styles.overlay} onClick={onClose}>
            <div className={styles.overlayPanel} onClick={(e) => e.stopPropagation()}>
                <div className={styles.overlayHeader}>
                    <div className={styles.overlayUrlBar}>
                        <LockIcon size={12} className={styles.overlayLockIcon} />
                        <span className={styles.overlayUrl} title={displayUrl}>
                            {displayUrl}
                        </span>
                    </div>
                    <button
                        className={styles.overlayCloseBtn}
                        onClick={onClose}
                        aria-label="Close overlay"
                    >
                        ✕
                    </button>
                </div>
                <div className={styles.overlayContent}>
                    {isHtml ? (
                        <iframe
                            className={styles.overlayFrame}
                            src={iframeSrc}
                            title={filename}
                        />
                    ) : text == null ? (
                        <div className={styles.statusText}>Loading...</div>
                    ) : isMarkdown ? (
                        <div className={styles.markdownContent}>
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
                        </div>
                    ) : (
                        <pre className={styles.plainText}>{text}</pre>
                    )}
                </div>
            </div>
        </div>,
        document.body
    );
}

export default function FilePreviewPanel({ item, onClose }) {
    const [isCollapsed, setIsCollapsed] = useState(false);
    const [fetchedText, setFetchedText] = useState(null);
    const [overlayOpen, setOverlayOpen] = useState(false);
    const { filename, content_type, content, path } = item;

    // Reset local state when a different item is loaded
    const itemKey = path || content;
    useEffect(() => {
        setIsCollapsed(false);
        setFetchedText(null);
        setOverlayOpen(false);
    }, [itemKey]);

    const text = useMemo(() => {
        if (content) return decodeText(content);
        return fetchedText;
    }, [content, fetchedText]);

    // Fetch text content from path when no inline content is provided
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

    // For HTML: prefer the container path (enables relative asset references),
    // fall back to a blob URL from inline content.
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
            // Only revoke blob: URLs, not container paths
            if (iframeSrc && iframeSrc.startsWith('blob:')) URL.revokeObjectURL(iframeSrc);
        };
    }, [iframeSrc]);

    return (
        <div className={styles.panel}>
            <div className={styles.header} onClick={() => setIsCollapsed((c) => !c)}>
                <div className={styles.headerLeft}>
                    <span className={styles.icon}>{isHtml ? '🌐' : '📄'}</span>
                    <span className={styles.title} title={filename}>{filename}</span>
                </div>
                <div className={styles.headerRight}>
                    <button
                        className={styles.expandBtn}
                        onClick={(e) => { e.stopPropagation(); setOverlayOpen(true); }}
                        aria-label="Open fullscreen"
                        title="Open fullscreen"
                    >
                        ⛶
                    </button>
                    <button
                        className={styles.collapseBtn}
                        aria-label={isCollapsed ? 'Expand' : 'Collapse'}
                    >
                        <ChevronIcon size={12} direction={isCollapsed ? 'down' : 'up'} />
                    </button>
                    <button
                        className={styles.closeBtn}
                        onClick={(e) => { e.stopPropagation(); onClose(); }}
                        aria-label="Close preview"
                    >
                        ✕
                    </button>
                </div>
            </div>

            {!isCollapsed && (
                <div className={styles.content}>
                    {isHtml ? (
                        <iframe
                            className={styles.htmlFrame}
                            src={iframeSrc}
                            title={filename}
                        />
                    ) : text == null ? (
                        <div className={styles.statusText}>Loading...</div>
                    ) : isMarkdown ? (
                        <div className={styles.markdownContent}>
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
                        </div>
                    ) : (
                        <pre className={styles.plainText}>{text}</pre>
                    )}
                </div>
            )}

            {overlayOpen && (
                <FilePreviewOverlay
                    iframeSrc={iframeSrc}
                    text={text}
                    isHtml={isHtml}
                    isMarkdown={isMarkdown}
                    filename={filename}
                    path={path}
                    onClose={() => setOverlayOpen(false)}
                />
            )}
        </div>
    );
}
