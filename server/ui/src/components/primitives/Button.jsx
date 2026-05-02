import styles from './Button.module.css';

/**
 * Canonical 32px text button matching the SIGNAL design language.
 *
 * Variants:
 *   outline (default) — secondary actions (Cancel, Back). Most buttons.
 *   filled            — single primary action per surface (Save, Connect).
 *   ghost             — tertiary / quiet (Skip, dismiss).
 *   danger            — destructive (Delete, Disconnect).
 *
 * Icon API is children-based: <Button><Icon /> Label</Button>.
 *
 * `type` defaults to "button" so this primitive does not accidentally
 * submit forms when dropped into a <form>.
 */
export default function Button({
    variant = 'outline',
    type = 'button',
    className,
    children,
    ...rest
}) {
    const cls = [styles.btn, styles[variant], className].filter(Boolean).join(' ');
    return (
        <button type={type} className={cls} {...rest}>
            {children}
        </button>
    );
}
