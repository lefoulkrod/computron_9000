import styles from './Callout.module.css';

const DEFAULT_ICON = {
    danger: 'bi-exclamation-circle',
    warning: 'bi-exclamation-triangle',
    info: 'bi-info-circle',
    success: 'bi-check-circle',
};

/**
 * Inline, panel-level status block. Pairs with Toast for transient
 * floating messages. See SIGNAL design language §11 for the spec.
 *
 * Tones drive the background tint and icon colour. Pass `children`
 * to add a structured body (Callout.List / Callout.Footnote).
 */
export default function Callout({
    tone = 'info',
    title,
    description,
    icon,
    onDismiss,
    children,
}) {
    const iconClass = icon ?? DEFAULT_ICON[tone] ?? DEFAULT_ICON.info;
    return (
        <div className={`${styles.callout} ${styles[tone]}`} role="alert">
            <div className={styles.head}>
                <i className={`bi ${iconClass} ${styles.icon}`} aria-hidden="true" />
                <div className={styles.body}>
                    {title && <div className={styles.title}>{title}</div>}
                    {description && <div className={styles.desc}>{description}</div>}
                </div>
                {onDismiss && (
                    <button
                        type="button"
                        className={styles.close}
                        onClick={onDismiss}
                        aria-label="Dismiss"
                    >
                        <i className="bi bi-x-lg" aria-hidden="true" />
                    </button>
                )}
            </div>
            {children}
        </div>
    );
}

function CalloutList({ children }) {
    return <ul className={styles.list}>{children}</ul>;
}

function CalloutItem({ kind, children }) {
    return (
        <li className={styles.item}>
            {kind && <span className={styles.kind}>{kind}</span>}
            <span className={styles.itemText}>{children}</span>
        </li>
    );
}

function CalloutFootnote({ children }) {
    return <div className={styles.footnote}>{children}</div>;
}

Callout.List = CalloutList;
Callout.Item = CalloutItem;
Callout.Footnote = CalloutFootnote;
