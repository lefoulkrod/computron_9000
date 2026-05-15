import { useRef, useEffect } from 'react';
import styles from './TerminalOutput.module.css';

export default function TerminalPanel({ lines }) {
    const bodyRef = useRef(null);

    useEffect(() => {
        if (bodyRef.current) {
            bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
        }
    }, [lines]);

    if (!lines || lines.length === 0) return null;

    return (
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
}
