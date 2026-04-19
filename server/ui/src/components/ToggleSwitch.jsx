import styles from './ToggleSwitch.module.css';

/**
 * SIGNAL toggle switch. 34×20 pill with accent highlight when on.
 *
 * Renders a native checkbox with role="switch" so assistive tech announces
 * it as an on/off control rather than a selection.
 *
 * Accessible name: this component does not render its own label. Callers
 * must either wrap it in a <label> whose text content names the control,
 * or pass an explicit aria-label. Without one of those, the switch has no
 * accessible name.
 */
export default function ToggleSwitch({ checked, onChange, disabled, ...rest }) {
    return (
        <span className={styles.control}>
            <input
                type="checkbox"
                role="switch"
                className={styles.input}
                checked={checked}
                onChange={onChange}
                disabled={disabled}
                {...rest}
            />
            <span className={styles.track} />
        </span>
    );
}
