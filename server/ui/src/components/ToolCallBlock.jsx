import styles from './ToolCallBlock.module.css';

/**
 * Tool-call line, rendered as the function call it is —
 * `› name(key="value", …)` in monospace. The leading chevron marks it as
 * something the agent ran. Argument values arrive already
 * whitespace-collapsed and length-capped (see _summarize_arguments /
 * _summarizeToolArgs); the row's CSS ellipsis is the final guard for narrow widths.
 */
export default function ToolCallBlock({ name, arguments: args }) {
    const pairs = args && typeof args === 'object' ? Object.entries(args) : [];
    return (
        <code className={styles.toolCall} data-testid="entry-tool-call">
            <span className={styles.marker} aria-hidden="true">›</span>
            <span className={styles.name}>{name}</span>
            <span className={styles.punct}>(</span>
            {pairs.length > 0 && (
                <span data-testid="tool-call-args">
                    {pairs.map(([key, value], i) => (
                        <span key={key}>
                            {i > 0 && <span className={styles.punct}>, </span>}
                            <span className={styles.key}>{key}=</span>
                            <span>{`"${value}"`}</span>
                        </span>
                    ))}
                </span>
            )}
            <span className={styles.punct}>)</span>
        </code>
    );
}
