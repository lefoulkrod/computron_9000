import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * Renders file content based on type and view mode.
 * Used by both FilePreviewInline and FullscreenPreview.
 *
 * @param {Object} props
 * @param {Object} props.item - File item with filename, content_type, content
 * @param {string} props.viewMode - 'source' or 'preview'
 * @param {string|null} props.text - Decoded text content
 * @param {boolean} props.isMarkdown
 * @param {boolean} props.isHtml
 * @param {boolean} props.isImageFile
 * @param {string|null} props.iframeSrc - URL for HTML iframe preview
 * @param {Object} props.styles - CSS module styles from the parent component
 * @returns {JSX.Element}
 */
export default function FileContentRenderer({
    item,
    viewMode,
    text,
    isMarkdown,
    isHtml,
    isImageFile,
    iframeSrc,
    styles,
}) {
    const { filename, content_type, content } = item;

    return (
        <>
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
                    {item.path && !content && (
                        <img src={item.path} alt={filename} className={styles.image} />
                    )}
                </div>
            )}
        </>
    );
}
