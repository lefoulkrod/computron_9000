import React, { useState, useEffect } from 'react';
import styles from './ToolProgressBlock.module.css';

/**
 * ToolProgressBlock displays real-time progress for long-running tools.
 *
 * Shows:
 * - A spinner for active stages
 * - The current stage label
 * - Optional progress bar (if progress_percent is provided)
 * - Optional output log (if showLog is true)
 */
export default function ToolProgressBlock({
    toolName,
    stage,
    stageLabel,
    message,
    progressPercent,
    output,
    showLog = false,
}) {
    const [logLines, setLogLines] = useState([]);
    const [isComplete, setIsComplete] = useState(false);

    // Parse output into log lines
    useEffect(() => {
        if (output) {
            const lines = output.split('\n').filter(line => line.trim() !== '');
            setLogLines(lines.slice(-50)); // Keep last 50 lines
        }
    }, [output]);

    // Check if tool is complete/failed
    useEffect(() => {
        if (stage === 'completed' || stage === 'failed') {
            setIsComplete(true);
        }
    }, [stage]);

    const stageText = stageLabel || stage || 'Running...';
    const hasProgress = progressPercent !== null && progressPercent !== undefined;
    const isRunning = !isComplete && stage !== 'failed';

    return (
        <div className={`${styles.progressBlock} ${isComplete ? styles.complete : ''}`}>
            <div className={styles.header}>
                <div className={styles.icon}>
                    {isRunning ? (
                        <Spinner />
                    ) : stage === 'failed' ? (
                        <ErrorIcon />
                    ) : (
                        <CheckIcon />
                    )}
                </div>
                <div className={styles.info}>
                    <span className={styles.toolName}>{toolName}</span>
                    <span className={styles.stage}>{stageText}</span>
                </div>
            </div>

            {hasProgress && (
                <div className={styles.progressBar}>
                    <div
                        className={styles.progressFill}
                        style={{ width: `${Math.min(100, Math.max(0, progressPercent))}%` }}
                    />
                </div>
            )}

            {message && (
                <div className={styles.message}>{message}</div>
            )}

            {showLog && logLines.length > 0 && (
                <div className={styles.logContainer}>
                    <pre className={styles.log}>
                        {logLines.join('\n')}
                    </pre>
                </div>
            )}
        </div>
    );
}

function Spinner() {
    return (
        <svg className={styles.spinner} viewBox="0 0 24 24">
            <circle
                className={styles.spinnerTrack}
                cx="12"
                cy="12"
                r="10"
                fill="none"
                strokeWidth="2"
            />
            <circle
                className={styles.spinnerArc}
                cx="12"
                cy="12"
                r="10"
                fill="none"
                strokeWidth="2"
            />
        </svg>
    );
}

function CheckIcon() {
    return (
        <svg className={styles.checkIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
    );
}

function ErrorIcon() {
    return (
        <svg className={styles.errorIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <circle cx="12" cy="12" r="10" strokeWidth={2} />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 9l-6 6M9 9l6 6" />
        </svg>
    );
}
