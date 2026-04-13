import { useState, useMemo, useEffect, useCallback } from 'react';

/**
 * Decodes base64 content to text.
 */
function _decodeText(b64) {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    return new TextDecoder().decode(bytes);
}

/**
 * Checks if the file can be previewed (markdown or HTML).
 */
function _canPreview(contentType, filename) {
    if (contentType === 'text/markdown' || contentType === 'text/x-markdown') return true;
    if (contentType === 'text/html') return true;
    if (filename?.endsWith('.md') || filename?.endsWith('.mdx')) return true;
    if (filename?.endsWith('.html') || filename?.endsWith('.htm')) return true;
    return false;
}

/**
 * Checks if the file is an image.
 */
export function isImage(contentType, filename) {
    if (contentType?.startsWith('image/')) return true;
    if (filename?.match(/\.(jpg|jpeg|png|gif|webp|svg)$/i)) return true;
    return false;
}

/**
 * Manages file content fetching, decoding, view mode, iframe blob URLs,
 * and download for both inline and fullscreen file previews.
 *
 * @param {Object} item - File item with filename, content_type, content, path
 * @returns {Object} Computed file content state and handlers
 */
export default function useFileContent(item) {
    const { filename, content_type, content, path } = item || {};

    const [fetchedText, setFetchedText] = useState(null);
    const [viewMode, setViewMode] = useState(() =>
        _canPreview(content_type, filename) ? 'preview' : 'source'
    );

    // Reset when item changes
    const itemKey = path || content;
    useEffect(() => {
        setFetchedText(null);
        setViewMode(_canPreview(content_type, filename) ? 'preview' : 'source');
    }, [itemKey, content_type, filename]);

    const text = useMemo(() => {
        if (content) return _decodeText(content);
        return fetchedText;
    }, [content, fetchedText]);

    // Fetch remote text content
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

    // Blob URL for HTML iframe preview
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

    const handleDownload = useCallback(() => {
        const link = document.createElement('a');
        if (text) {
            const blob = new Blob([text], { type: content_type || 'text/plain' });
            link.href = URL.createObjectURL(blob);
        } else if (path) {
            link.href = path;
        }
        link.download = filename || 'file';
        link.click();
        setTimeout(() => URL.revokeObjectURL(link.href), 100);
    }, [text, content_type, path, filename]);

    return {
        text,
        viewMode,
        setViewMode,
        isHtml,
        isMarkdown,
        showToggle,
        isImageFile,
        iframeSrc,
        handleDownload,
    };
}
