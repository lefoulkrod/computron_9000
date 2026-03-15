import { useState, useMemo, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import PreviewShell from './PreviewShell.jsx';
import styles from './FilePreview.module.css';
import LockIcon from './icons/LockIcon.jsx';

function decodeText(b64) {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    return new TextDecoder().decode(bytes);
}

function FileOverlayContent({ iframeSrc, text, isHtml, isMarkdown, filename, path }) {
    const displayUrl = path || filename;

    return (
        <>
            <div className={styles.overlayUrlBar}>
                <LockIcon size={12} className={styles.overlayLockIcon} />
                <span className={styles.overlayUrl} title={displayUrl}>
                    {displayUrl}
                </span>
            </div>
            <div className={styles.overlayBody}>
                {isHtml ? (
                    <iframe className={styles.overlayFrame} src={iframeSrc} title={filename} />
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
        </>
    );
}

export default function FilePreview({ item, onClose }) {
    const [fetchedText, setFetchedText] = useState(null);
    const { filename, content_type, content, path } = item;

    const itemKey = path || content;
    useEffect(() => {
        setFetchedText(null);
    }, [itemKey]);

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

    const icon = isHtml ? '\u{1F310}' : '\u{1F4C4}';

    return (
        <PreviewShell
            icon={icon}
            title={filename}
            onClose={onClose}
            expandContent={
                <FileOverlayContent
                    iframeSrc={iframeSrc}
                    text={text}
                    isHtml={isHtml}
                    isMarkdown={isMarkdown}
                    filename={filename}
                    path={path}
                />
            }
        >
            <div className={styles.content}>
                {isHtml ? (
                    <iframe className={styles.htmlFrame} src={iframeSrc} title={filename} />
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
        </PreviewShell>
    );
}
