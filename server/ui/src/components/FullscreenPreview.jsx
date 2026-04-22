import { useEffect, useCallback, useState } from 'react';
import styles from './FullscreenPreview.module.css';
import ArrowLeftIcon from './icons/ArrowLeftIcon.jsx';
import DownloadIcon from './icons/DownloadIcon.jsx';
import SourceIcon from './icons/SourceIcon.jsx';
import EyeIcon from './icons/EyeIcon.jsx';
import CopyIcon from './icons/CopyIcon.jsx';
import FileContentRenderer from './FileContentRenderer.jsx';
import useFileContent from '../hooks/useFileContent.js';

export default function FullscreenPreview({ item, onClose }) {
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
        handleCopy,
        canCopy,
    } = useFileContent(item);

    const [copied, setCopied] = useState(false);
    const onCopyClick = async () => {
        const ok = await handleCopy();
        if (!ok) return;
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    const { filename } = item;

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
        <div className={styles.fullscreenPreview} data-testid="fullscreen-preview">
            {/* Header bar */}
            <div className={styles.header}>
                <div className={styles.headerLeft}>
                    <button
                        className={styles.backBtn}
                        onClick={onClose}
                        title="Back"
                        aria-label="Back to preview panel"
                        data-testid="fullscreen-back"
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
                    {showToggle && !isPdf && (
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
                    {canCopy && (
                        <button
                            className={styles.headerBtn}
                            onClick={onCopyClick}
                            title={copied ? 'Copied!' : 'Copy to clipboard'}
                            aria-label="Copy file contents to clipboard"
                        >
                            <CopyIcon size={14} />
                        </button>
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
                    isPdf={isPdf}
                    iframeSrc={iframeSrc}
                    pdfSrc={pdfSrc}
                    styles={styles}
                />
            </div>
        </div>
    );
}
