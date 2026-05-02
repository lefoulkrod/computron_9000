import { useState } from 'react';
import styles from './FileFullscreen.module.css';
import DownloadIcon from './icons/DownloadIcon.jsx';
import SourceIcon from './icons/SourceIcon.jsx';
import EyeIcon from './icons/EyeIcon.jsx';
import CopyIcon from './icons/CopyIcon.jsx';
import FileContentRenderer from './FileContentRenderer.jsx';
import FullscreenPreview from './FullscreenPreview.jsx';
import IconButton from './primitives/IconButton.jsx';
import useFileContent from '../hooks/useFileContent.js';

export default function FileFullscreen({ item, onClose }) {
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

    const headerActions = (
        <>
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
                <IconButton
                    size="md"
                    onClick={onCopyClick}
                    title={copied ? 'Copied!' : 'Copy to clipboard'}
                    aria-label="Copy file contents to clipboard"
                >
                    <CopyIcon size={14} />
                </IconButton>
            )}
            <IconButton
                size="md"
                onClick={handleDownload}
                title="Download"
                aria-label="Download file"
            >
                <DownloadIcon size={14} />
            </IconButton>
        </>
    );

    return (
        <FullscreenPreview
            title={filename || 'File'}
            onClose={onClose}
            headerActions={headerActions}
        >
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
        </FullscreenPreview>
    );
}
