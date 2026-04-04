import PreviewShell from './PreviewShell.jsx';
import styles from './GenerationPreview.module.css';

export default function GenerationPreview({ preview, onClose }) {
    if (!preview) return null;

    const { media_type, status, step, total_steps, message } = preview;
    const previewImage = preview.preview;
    const output = preview.output;
    const outputPath = preview.output_path;
    const outputContentType = preview.output_content_type || '';

    const isImage = media_type === 'image';
    const isAudio = media_type === 'audio';
    const isVideo = !isImage && !isAudio;

    const LABELS = { image: 'Image', video: 'Video', audio: 'Music' };
    const label = LABELS[media_type] || 'Media';

    const progressPct = (step != null && total_steps)
        ? Math.round((step / total_steps) * 100)
        : 0;

    const isComplete = status === 'complete';
    const isFailed = status === 'failed';
    const isVideoContent = outputContentType.startsWith('video/');
    const isAudioContent = isAudio || outputContentType.startsWith('audio/');
    const hasOutput = output || outputPath;
    const outputSrc = outputPath || (output ? `data:${outputContentType};base64,${output}` : null);

    const handleDownload = () => {
        if (!outputSrc) return;
        const link = document.createElement('a');
        link.href = outputSrc;
        const ext = isAudioContent ? 'wav' : isVideoContent ? 'mp4' : 'png';
        link.download = `generated_${Date.now()}.${ext}`;
        link.click();
    };

    const ICONS = { image: '\u{1F5BC}', video: '\u{1F3AC}', audio: '\u{1F3B5}' };
    const icon = ICONS[media_type] || '\u{1F3AC}';
    const displayTitle = isComplete ? `${label} Generated` : `Generating ${label}`;

    const expandContent = isComplete && hasOutput && outputSrc ? (
        isAudioContent ? (
            <audio src={outputSrc} controls autoPlay className={styles.expandedMedia} />
        ) : isVideoContent ? (
            <video src={outputSrc} controls autoPlay loop className={styles.expandedMedia} />
        ) : (
            <img src={outputSrc} alt="Generated" className={styles.expandedMedia} />
        )
    ) : undefined;

    return (
        <PreviewShell
            icon={icon}
            title={displayTitle}
            onClose={onClose}
            expandContent={expandContent}
        >
            <div className={styles.content}>
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

                {isFailed && (
                    <div className={styles.errorMessage}>
                        {message || 'Generation failed'}
                    </div>
                )}

                {!isComplete && previewImage && (
                    <div className={styles.previewContainer}>
                        <img
                            src={`data:image/jpeg;base64,${previewImage}`}
                            alt="Generation preview"
                            className={styles.previewImage}
                        />
                    </div>
                )}

                {isComplete && hasOutput && isImage && (
                    <div className={styles.previewContainer}>
                        <img src={outputSrc} alt="Generated image" className={styles.previewImage} />
                        <button className={styles.downloadBtn} onClick={handleDownload}>
                            Download
                        </button>
                    </div>
                )}

                {isComplete && hasOutput && isVideoContent && (
                    <div className={styles.previewContainer}>
                        <video src={outputSrc} controls autoPlay loop className={styles.previewVideo} />
                        <button className={styles.downloadBtn} onClick={handleDownload}>
                            Download
                        </button>
                    </div>
                )}

                {isComplete && hasOutput && isAudioContent && (
                    <div className={styles.previewContainer}>
                        <button className={styles.downloadBtn} onClick={handleDownload}>
                            Download
                        </button>
                    </div>
                )}

                {isComplete && !hasOutput && (
                    <div className={styles.statusText}>
                        {message || 'Generation complete'}
                    </div>
                )}
            </div>
        </PreviewShell>
    );
}
