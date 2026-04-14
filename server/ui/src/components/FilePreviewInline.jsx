import styles from './FilePreviewInline.module.css';
import FileIcon from './icons/FileIcon.jsx';
import ImageIcon from './icons/ImageIcon.jsx';
import DownloadIcon from './icons/DownloadIcon.jsx';
import ExpandIcon from './icons/ExpandIcon.jsx';
import SourceIcon from './icons/SourceIcon.jsx';
import EyeIcon from './icons/EyeIcon.jsx';
import FileContentRenderer from './FileContentRenderer.jsx';
import useFileContent from '../hooks/useFileContent.js';

function getFileIcon(contentType, filename) {
    if (contentType?.startsWith('image/') || filename?.match(/\.(jpg|jpeg|png|gif|webp|svg)$/i)) {
        return <ImageIcon size={14} />;
    }
    if (contentType?.startsWith('text/') || filename?.match(/\.(js|jsx|ts|tsx|py|java|cpp|c|h|go|rs|rb|php|html|css|json|xml|yaml|yml|md|txt)$/i)) {
        return <SourceIcon size={14} />;
    }
    return <FileIcon size={14} />;
}

export default function FilePreviewInline({ item, onFullscreen }) {
    const {
        text,
        viewMode,
        setViewMode,
        isHtml,
        isMarkdown,
        showToggle,
        isImageFile,
        isPdf,
        pdfSrc,
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
                    {showToggle && !isPdf && (
                        <div className={styles.toggle} data-testid="file-view-toggle">
                            <button
                                className={`${styles.toggleBtn} ${viewMode === 'source' ? styles.toggleBtnActive : ''}`}
                                onClick={() => setViewMode('source')}
                                data-testid="file-view-source"
                            >
                                <SourceIcon size={12} />
                                Source
                            </button>
                            <button
                                className={`${styles.toggleBtn} ${viewMode === 'preview' ? styles.toggleBtnActive : ''}`}
                                onClick={() => setViewMode('preview')}
                                data-testid="file-view-preview"
                            >
                                <EyeIcon size={12} />
                                Preview
                            </button>
                        </div>
                    )}
                    {!showToggle && !isPdf && (
                        <div className={styles.toggle} data-testid="file-view-source-only">
                            <button className={`${styles.toggleBtn} ${styles.toggleBtnActive}`}>
                                <SourceIcon size={12} /> Source
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
                        data-testid="file-download"
                    >
                        <DownloadIcon size={14} />
                    </button>
                    {onFullscreen && (
                        <button
                            className={styles.toolbarBtn}
                            onClick={onFullscreen}
                            title="Fullscreen"
                            aria-label="Open fullscreen"
                            data-testid="file-fullscreen"
                        >
                            <ExpandIcon size={14} />
                        </button>
                    )}
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
                    isPdf={isPdf}
                    iframeSrc={iframeSrc}
                    pdfSrc={pdfSrc}
                    styles={styles}
                />
            </div>
        </div>
    );
}
