import { useEffect, useCallback } from 'react';
import styles from './FullscreenPreview.module.css';
import ArrowLeftIcon from './icons/ArrowLeftIcon.jsx';
import DownloadIcon from './icons/DownloadIcon.jsx';
import SourceIcon from './icons/SourceIcon.jsx';
import EyeIcon from './icons/EyeIcon.jsx';
import FileContentRenderer from './FileContentRenderer.jsx';
import useFileContent from '../hooks/useFileContent.js';

/**
 * Full viewport takeover for file previews (NOT a lightbox overlay).
 *
 * @param {Object} props
 * @param {Object} props.item - File item with filename, content_type, content, path
 * @param {function(): void} props.onClose - Callback to close fullscreen view
 * @returns {JSX.Element}
 */
export default function FullscreenPreview({ item, onClose }) {
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

    const { filename } = item;

    // Escape key closes the fullscreen view
    const handleKeyDown = useCallback((e) => {
        if (e.key === 'Escape') {
            onClose();
        }
    }, [onClose]);

    useEffect(() => {
        document.addEventListener('keydown', handleKeyDown);
        return () => document.removeEventListener('keydown', handleKeyDown);
    }, [handleKeyDown]);

    return (
        <div className={styles.fullscreenPreview}>
            {/* Header bar */}
            <div className={styles.header}>
                <div className={styles.headerLeft}>
                    <button
                        className={styles.backBtn}
                        onClick={onClose}
                        title="Back"
                        aria-label="Back to preview panel"
                    >
                        <ArrowLeftIcon size={14} />
                        Back
                    </button>
                </div>

                <div className={styles.headerCenter}>
                    <span className={styles.filename} title={filename}>
                        {filename || 'File'}
                    </span>
                </div>

                <div className={styles.headerRight}>
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
                    <button
                        className={styles.headerBtn}
                        onClick={handleDownload}
                        title="Download"
                        aria-label="Download file"
                    >
                        <DownloadIcon size={14} />
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
