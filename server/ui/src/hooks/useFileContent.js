import { useState, useMemo, useEffect, useCallback } from 'react';
import { hasPreviewToggle, isImageFile, isPdfFile } from '../utils/fileTypes.js';

function _decodeText(b64) {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    return new TextDecoder().decode(bytes);
}

export default function useFileContent(item) {
    const { filename, content_type, content, path } = item || {};

    const [fetchedText, setFetchedText] = useState(null);
    const [viewMode, setViewMode] = useState(() =>
        hasPreviewToggle(content_type, filename) ? 'preview' : 'source'
    );

    const itemKey = path || content;
    useEffect(() => {
        setFetchedText(null);
        setViewMode(hasPreviewToggle(content_type, filename) ? 'preview' : 'source');
    }, [itemKey, content_type, filename]);

    const isImage = isImageFile(content_type, filename);
    const isPdf = isPdfFile(content_type, filename);
    const isHtml = content_type === 'text/html';
    const isMarkdown =
        content_type === 'text/markdown' ||
        content_type === 'text/x-markdown' ||
        (!isHtml && filename && (filename.endsWith('.md') || filename.endsWith('.mdx')));
    const showToggle = isHtml || isMarkdown;

    const text = useMemo(() => {
        // Don't decode binary content (images, PDFs) as text
        if (isImage || isPdf) return null;
        if (content) return _decodeText(content);
        return fetchedText;
    }, [content, fetchedText, isImage, isPdf]);

    // Fetch remote text content (not for images or PDFs)
    useEffect(() => {
        if (isImage || isPdf || content || !path) return;
        let cancelled = false;
        fetch(path).then(r => r.text()).then(t => {
            if (!cancelled) setFetchedText(t);
        });
        return () => { cancelled = true; };
    }, [content, path, isImage, isPdf]);

    // Blob URL for HTML iframe preview
    const iframeSrc = useMemo(() => {
        if (isHtml && path) return path;
        if (isHtml && text) {
            const blob = new Blob([text], { type: 'text/html' });
            return URL.createObjectURL(blob);
        }
        return null;
    }, [isHtml, path, text]);

    // Blob/path URL for PDF preview
    const pdfSrc = useMemo(() => {
        if (!isPdf) return null;
        if (path) return path;
        if (content) {
            const byteChars = atob(content);
            const bytes = new Uint8Array(byteChars.length);
            for (let i = 0; i < byteChars.length; i++) bytes[i] = byteChars.charCodeAt(i);
            const blob = new Blob([bytes], { type: 'application/pdf' });
            return URL.createObjectURL(blob);
        }
        return null;
    }, [isPdf, path, content]);

    useEffect(() => {
        return () => {
            if (iframeSrc && iframeSrc.startsWith('blob:')) URL.revokeObjectURL(iframeSrc);
            if (pdfSrc && pdfSrc.startsWith('blob:')) URL.revokeObjectURL(pdfSrc);
        };
    }, [iframeSrc, pdfSrc]);

    const handleDownload = useCallback(() => {
        const link = document.createElement('a');
        if (text) {
            const blob = new Blob([text], { type: content_type || 'text/plain' });
            link.href = URL.createObjectURL(blob);
        } else if (path) {
            link.href = path;
        } else if (content) {
            const byteChars = atob(content);
            const bytes = new Uint8Array(byteChars.length);
            for (let i = 0; i < byteChars.length; i++) bytes[i] = byteChars.charCodeAt(i);
            const blob = new Blob([bytes], { type: content_type || 'application/octet-stream' });
            link.href = URL.createObjectURL(blob);
        }
        link.download = filename || 'file';
        link.click();
        setTimeout(() => URL.revokeObjectURL(link.href), 100);
    }, [text, content, content_type, path, filename]);

    return {
        text,
        viewMode,
        setViewMode,
        isHtml,
        isMarkdown,
        showToggle,
        isImageFile: isImage,
        isPdf,
        pdfSrc,
        iframeSrc,
        handleDownload,
    };
}
