import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function FileContentRenderer({
    item,
    viewMode,
    text,
    isMarkdown,
    isHtml,
    isImageFile,
    isPdf,
    iframeSrc,
    pdfSrc,
    styles,
}) {
    const { filename, content_type, content } = item;

    return (
        <>
            {isPdf && pdfSrc && (
                <iframe
                    className={styles.pdfFrame || styles.htmlFrame}
                    src={pdfSrc}
                    title={filename}
                />
            )}
            {isPdf && !pdfSrc && (
                <div className={styles.statusText}>Loading...</div>
            )}
            {!isPdf && viewMode === 'source' && (
                <pre className={styles.sourceCode}>{text || 'Loading...'}</pre>
            )}
            {!isPdf && viewMode === 'preview' && isMarkdown && text && (
                <div className={styles.markdownContent}>
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
                </div>
            )}
            {!isPdf && viewMode === 'preview' && isMarkdown && !text && (
                <div className={styles.statusText}>Loading...</div>
            )}
            {!isPdf && viewMode === 'preview' && isHtml && iframeSrc && (
                <iframe
                    className={styles.htmlFrame}
                    src={iframeSrc}
                    title={filename}
                    sandbox="allow-scripts allow-same-origin"
                />
            )}
            {!isPdf && viewMode === 'preview' && isHtml && !iframeSrc && (
                <div className={styles.statusText}>Loading...</div>
            )}
            {!isPdf && viewMode === 'preview' && isImageFile && (
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
