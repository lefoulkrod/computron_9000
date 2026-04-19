import styles from './Badge.module.css';

const VARIANT = {
    success: styles.success,
    info: styles.info,
    danger: styles.danger,
    warning: styles.warning,
    neutral: styles.neutral,
};

/**
 * Small status / tag pill per the SIGNAL design language.
 * Brand monospace, uppercase-friendly, radius-sm, 10px.
 *
 * @param {Object} props
 * @param {'success'|'info'|'danger'|'warning'|'neutral'} [props.variant='neutral']
 * @param {string} [props.className]
 * @param {React.ReactNode} props.children
 */
export default function Badge({ variant = 'neutral', className = '', children, ...rest }) {
    const variantClass = VARIANT[variant] || styles.neutral;
    return (
        <span className={`${styles.badge} ${variantClass} ${className}`} {...rest}>
            {children}
        </span>
    );
}
