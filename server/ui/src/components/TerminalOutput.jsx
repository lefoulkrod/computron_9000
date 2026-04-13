import { useRef, useEffect, useState } from 'react';
import styles from './TerminalOutput.module.css';
import ChevronIcon from './icons/ChevronIcon.jsx';

/**
 * Terminal output component showing command execution results.
 *
 * @param {Object} props
 * @param {Array} props.lines - Array of terminal line objects
 * @param {function(): void} [props.onClose] - Callback when close button clicked
 * @param {boolean} [props.hideShell] - If true, render without header/collapse wrapper
 * @returns {JSX.Element|null}
 */
export default function TerminalPanel({ lines, onClose, hideShell }) {
    const bodyRef = useRef(null);
    const [isCollapsed, setIsCollapsed] = useState(false);

    useEffect(() => {
        if (!isCollapsed && bodyRef.current) {
            bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
        }
    }, [lines, isCollapsed]);

    if (!lines || lines.length === 0) return null;

    const content = (
        <div className={styles.body} ref={bodyRef}>
            {lines.map((item, i) => {
                const isRunning = item.status === 'running';
                const isStreaming = item.status === 'streaming';
                const isActive = isRunning || isStreaming;
                const hasOutput = item.stdout || item.stderr;
                const exitOk = item.exit_code === 0 || item.exit_code === null || item.exit_code === undefined;
                return (
                    <div key={item.cmd_id || i} className={styles.entry}>
                        <div className={styles.cmdLine}>
                            <span className={styles.prompt}>$</span>
                            <span className={styles.cmd}>{item.cmd}</span>
                            {isActive && (
                                <span className={styles.runningBadge}>running</span>
                            )}
                            {!isActive && !hasOutput && exitOk && (
                                <span className={styles.okBadge}>ok</span>
                            )}
                            {!isActive && item.exit_code !== null && item.exit_code !== undefined && item.exit_code !== 0 && (
                                <span className={styles.exitBadge}>exit {item.exit_code}</span>
                            )}
                        </div>
                        {item.stdout && (
                            <pre className={styles.stdout}>{item.stdout}</pre>
                        )}
                        {item.stderr && (
                            <pre className={styles.stderr}>{item.stderr}</pre>
                        )}
                    </div>
                );
            })}
        </div>
    );

    if (hideShell) {
        return content;
    }

    return (
        <div className={styles.panel}>
            <div className={styles.header} onClick={() => setIsCollapsed((c) => !c)}>
                <div className={styles.headerLeft}>
                    <span className={styles.dot} style={{ background: '#ff5f57' }} />
                    <span className={styles.dot} style={{ background: '#febc2e' }} />
                    <span className={styles.dot} style={{ background: '#28c840' }} />
                    <span className={styles.title}>Terminal</span>
                </div>
                <div className={styles.headerRight}>
                    <button
                        className={styles.collapseBtn}
                        aria-label={isCollapsed ? 'Expand' : 'Collapse'}
                    >
                        <ChevronIcon size={12} direction={isCollapsed ? 'down' : 'up'} />
                    </button>
                    <button
                        className={styles.closeBtn}
                        onClick={(e) => { e.stopPropagation(); onClose(); }}
                        aria-label="Close terminal"
                    >
                        ×
                    </button>
                </div>
            </div>
            {!isCollapsed && content}
        </div>
    );
}
