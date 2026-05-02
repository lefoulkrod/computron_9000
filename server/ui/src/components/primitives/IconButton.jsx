import styles from './IconButton.module.css';

export default function IconButton({
    size = 'sm',
    className,
    children,
    ...rest
}) {
    const cls = [styles.btn, styles[size], className].filter(Boolean).join(' ');
    return (
        <button type="button" className={cls} {...rest}>
            {children}
        </button>
    );
}
