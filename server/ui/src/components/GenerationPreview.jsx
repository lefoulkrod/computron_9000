import React, { useState } from 'react';
import styles from './GenerationPreview.module.css';
import ChevronIcon from './icons/ChevronIcon.jsx';

export default function GenerationPreview({ preview, onClose }) {
    const [isCollapsed, setIsCollapsed] = useState(false);

    if (!preview) return null;

    const { media_type, status, step, total_steps, message } = preview;
    const previewImage = preview.preview;
    const output = preview.output;
    const outputPath = preview.output_path;
    const outputContentType = preview.output_content_type || '';

    const isImage = media_type === 'image';
    const title = isImage ? 'Generating Image' : 'Generating Video';

    const progressPct = (step != null && total_steps)
        ? Math.round((step / total_steps) * 100)
        : 0;

    const isComplete = status === 'complete';
    const isFailed = status === 'failed';
    const isVideo = outputContentType.startsWith('video/');
    const hasOutput = output || outputPath;
    const outputSrc = outputPath || (output ? `data:${outputContentType};base64,${output}` : null);

    const handleDownload = () => {
        if (!outputSrc) return;
        const link = document.createElement('a');
        link.href = outputSrc;
        const ext = isVideo ? 'mp4' : 'png';
        link.download = `generated_${Date.now()}.${ext}`;
        link.click();
    };

    return (
        <div className={styles.panel}>
            <div className={styles.header} onClick={() => setIsCollapsed(c => !c)}>
                <div className={styles.headerLeft}>
                    <span className={styles.icon}>
                        {isImage ? '🖼' : '🎬'}
                    </span>
                    <span className={styles.title}>
                        {isComplete ? (isImage ? 'Image Generated' : 'Video Generated') : title}
                    </span>
                </div>
                <div className={styles.headerRight}>
                    <button className={styles.collapseBtn} aria-label={isCollapsed ? 'Expand' : 'Collapse'}>
                        <ChevronIcon size={12} direction={isCollapsed ? 'down' : 'up'} />
                    </button>
                    {onClose && (
                        <button
                            className={styles.closeBtn}
                            onClick={(e) => { e.stopPropagation(); onClose(); }}
                            aria-label="Close"
                        >
                            ✕
                        </button>
                    )}
                </div>
            </div>

            {!isCollapsed && (
                <div className={styles.content}>
                    {/* Progress bar */}
                    {!isComplete && !isFailed && (
                        <div className={styles.progressSection}>
                            <div className={styles.progressBar}>
                                <div
                                    className={styles.progressFill}
                                    style={{ width: `${progressPct}%` }}
                                />
                            </div>
                            <div className={styles.statusText}>
                                {message || (status === 'loading' ? 'Loading model...' : `Step ${step || 0}/${total_steps || '?'}`)}
                            </div>
                        </div>
                    )}

                    {/* Failed state */}
                    {isFailed && (
                        <div className={styles.errorMessage}>
                            {message || 'Generation failed'}
                        </div>
                    )}

                    {/* Preview image (during generation) */}
                    {!isComplete && previewImage && (
                        <div className={styles.previewContainer}>
                            <img
                                src={`data:image/jpeg;base64,${previewImage}`}
                                alt="Generation preview"
                                className={styles.previewImage}
                            />
                        </div>
                    )}

                    {/* Complete state — image */}
                    {isComplete && hasOutput && !isVideo && (
                        <div className={styles.previewContainer}>
                            <img
                                src={outputSrc}
                                alt="Generated image"
                                className={styles.previewImage}
                            />
                            <button className={styles.downloadBtn} onClick={handleDownload}>
                                Download
                            </button>
                        </div>
                    )}

                    {/* Complete state — video */}
                    {isComplete && hasOutput && isVideo && (
                        <div className={styles.previewContainer}>
                            <video
                                src={outputSrc}
                                controls
                                autoPlay
                                loop
                                className={styles.previewVideo}
                            />
                            <button className={styles.downloadBtn} onClick={handleDownload}>
                                Download
                            </button>
                        </div>
                    )}

                    {/* Complete without output data */}
                    {isComplete && !hasOutput && (
                        <div className={styles.statusText}>
                            {message || 'Generation complete'}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
