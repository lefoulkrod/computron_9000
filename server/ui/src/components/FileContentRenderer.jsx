import { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { highlightCode } from '../utils/highlight.js';
import { PreCodeBlock, InlineCode } from './CodeBlock.jsx';

const _markdownComponents = {
    pre: (props) => <PreCodeBlock {...props} />,
    code: (props) => <InlineCode {...props} />,
};

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

    const highlightedSource = useMemo(() => {
        if (!text || isPdf) return null;
        return highlightCode(text, { filename, contentType: content_type });
    }, [text, isPdf, filename, content_type]);

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
                highlightedSource ? (
                    <pre className={styles.sourceCode}>
                        <code
                            className="hljs"
                            dangerouslySetInnerHTML={{ __html: highlightedSource.html }}
                        />
                    </pre>
                ) : (
                    <pre className={styles.sourceCode}>Loading...</pre>
                )
            )}
            {!isPdf && viewMode === 'preview' && isMarkdown && text && (
                <div className={styles.markdownContent}>
                    <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={_markdownComponents}
                    >
                        {text}
                    </ReactMarkdown>
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
