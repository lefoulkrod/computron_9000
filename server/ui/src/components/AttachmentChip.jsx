import React from 'react';
import styles from './AttachmentChip.module.css';

const _CODE_EXT = new Set([
    'js', 'jsx', 'ts', 'tsx', 'py', 'go', 'rs', 'java', 'c', 'cpp', 'h',
    'css', 'html', 'json', 'sh', 'sql', 'yml', 'yaml', 'toml',
]);
const _DOC_EXT = new Set(['md', 'txt', 'doc', 'docx', 'rtf', 'csv']);

/** Pick an icon + colour tint for a non-image attachment from its extension. */
function _fileKind(filename) {
    const ext = (filename?.split('.').pop() || '').toLowerCase();
    const label = ext ? ext.toUpperCase() : 'FILE';
    if (ext === 'pdf') return { icon: 'bi-file-earmark-pdf', tint: styles.tintPdf, label };
    if (_CODE_EXT.has(ext)) return { icon: 'bi-file-earmark-code', tint: styles.tintCode, label };
    if (_DOC_EXT.has(ext)) return { icon: 'bi-file-earmark-text', tint: styles.tintDoc, label };
    return { icon: 'bi-file-earmark', tint: styles.tintDoc, label };
}

function _formatSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * One attachment preview — a 60×60 image thumbnail or a type-tinted file
 * card. Shared by the composer (with `onRemove`) and sent chat messages
 * (read-only). An image is rendered when `src` is given, otherwise a file
 * card; `sizeBytes` is shown in the file meta when known.
 */
export default function AttachmentChip({ src, filename, sizeBytes, onRemove }) {
    if (src) {
        return (
            <div className={styles.image}>
                <img src={src} alt={filename || 'attachment'} data-testid="attachment-image" />
                {onRemove && (
                    <button
                        type="button"
                        className={styles.removeImage}
                        onClick={onRemove}
                        aria-label="Remove attachment"
                        title="Remove attachment"
                    >
                        <i className="bi bi-x" />
                    </button>
                )}
            </div>
        );
    }

    const kind = _fileKind(filename);
    const meta = sizeBytes != null ? `${kind.label} · ${_formatSize(sizeBytes)}` : kind.label;

    return (
        <div className={styles.file} data-testid="attachment-file">
            <span className={`${styles.icon} ${kind.tint}`}>
                <i className={`bi ${kind.icon}`} />
            </span>
            <span className={styles.meta}>
                <span className={styles.name}>{filename}</span>
                <span className={styles.sub}>{meta}</span>
            </span>
            {onRemove && (
                <button
                    type="button"
                    className={styles.removeFile}
                    onClick={onRemove}
                    aria-label="Remove attachment"
                    title="Remove attachment"
                >
                    <i className="bi bi-x-lg" />
                </button>
            )}
        </div>
    );
}
