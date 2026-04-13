import styles from './FilePreviewInline.module.css';
import FileIcon from './icons/FileIcon.jsx';
import DownloadIcon from './icons/DownloadIcon.jsx';
import ExpandIcon from './icons/ExpandIcon.jsx';
import SourceIcon from './icons/SourceIcon.jsx';
import EyeIcon from './icons/EyeIcon.jsx';
import FileContentRenderer from './FileContentRenderer.jsx';
import useFileContent, { isImage } from '../hooks/useFileContent.js';

/**
 * Gets the appropriate file icon based on content type.
 *
 * @param {string} contentType - MIME type
 * @param {string} filename - File name
 * @returns {JSX.Element}
 */
function getFileIcon(contentType, filename) {
    if (contentType?.startsWith('image/') || filename?.match(/\.(jpg|jpeg|png|gif|webp|svg)$/i)) {
        return (
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="1" y="2" width="14" height="12" rx="1" stroke="currentColor" strokeWidth="1.2"/>
                <circle cx="5" cy="6" r="1.5" fill="currentColor"/>
                <path d="M1 12l4-4 3 3 3-3 4 4" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/>
            </svg>
        );
    }
    if (contentType?.startsWith('text/') || filename?.match(/\.(js|jsx|ts|tsx|py|java|cpp|c|h|go|rs|rb|php|html|css|json|xml|yaml|yml|md|txt)$/i)) {
        return <SourceIcon size={14} />;
    }
    return <FileIcon size={14} />;
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
    const {
        text,
        viewMode,
        setViewMode,
        isHtml,
        isMarkdown,
        showToggle,
        isImageFile,
        iframeSrc,
        handleDownload,
    } = useFileContent(item);

    const { filename, content_type } = item;
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
                <FileContentRenderer
                    item={item}
                    viewMode={viewMode}
                    text={text}
                    isMarkdown={isMarkdown}
                    isHtml={isHtml}
                    isImageFile={isImageFile}
                    iframeSrc={iframeSrc}
                    styles={styles}
                />
            </div>
        </div>
    );
}
