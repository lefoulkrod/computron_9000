import { useCallback, useEffect, useRef, useState } from 'react';

import styles from './ConfirmButton.module.css';

/**
 * A button that requires two clicks to fire its action.
 *
 * First click flips into the "confirming" state — the label changes and
 * the button shifts to the design language's danger palette — and starts
 * a timer that auto-disarms after `timeout` ms. A second click within
 * that window calls `onConfirm`. If `onConfirm` returns a promise, the
 * button enters a "busy" state (disabled, optional `busyLabel`) until
 * the promise resolves or rejects.
 *
 * Default styling matches the design language's `.btn` baseline plus a
 * compact icon-first footprint. Callers can pass `className` to override
 * sizing/colors and `confirmClassName` to override the confirming palette.
 */
export default function ConfirmButton({
    onConfirm,
    label,
    confirmLabel = 'Confirm?',
    busyLabel,
    icon,
    timeout = 3000,
    className,
    confirmClassName,
    disabled = false,
    title,
    'data-testid': testid,
}) {
    const [confirming, setConfirming] = useState(false);
    const [busy, setBusy] = useState(false);
    // A long-running onConfirm could resolve after the user navigates away;
    // guard setState so React doesn't warn about updating an unmounted node.
    const mounted = useRef(true);
    useEffect(() => () => { mounted.current = false; }, []);

    const handleClick = useCallback(async () => {
        if (!confirming) {
            setConfirming(true);
            setTimeout(() => {
                if (mounted.current) setConfirming(false);
            }, timeout);
            return;
        }
        setBusy(true);
        try {
            await onConfirm();
        } finally {
            if (mounted.current) {
                setBusy(false);
                setConfirming(false);
            }
        }
    }, [confirming, onConfirm, timeout]);

    const text = busy ? (busyLabel ?? label) : confirming ? confirmLabel : label;
    const composedClass = [
        styles.btn,
        className,
        confirming ? (confirmClassName ?? styles.confirming) : '',
    ].filter(Boolean).join(' ');

    return (
        <button
            type="button"
            className={composedClass}
            onClick={handleClick}
            disabled={disabled || busy}
            title={confirming ? 'Click again to confirm' : title}
            data-testid={testid}
        >
            {icon && <i className={`bi ${icon}`} />}
            {text}
        </button>
    );
}
