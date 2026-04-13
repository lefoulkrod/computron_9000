import { useEffect, useRef } from 'react';
import styles from './SplitHandle.module.css';

/**
 * A draggable vertical divider between chat and preview columns.
 *
 * @param {Object} props
 * @param {function(number): void} props.onDrag - Callback that receives the new split percentage (20-80)
 * @returns {JSX.Element}
 */
export default function SplitHandle({ onDrag }) {
    const handleRef = useRef(null);
    const onDragRef = useRef(onDrag);
    onDragRef.current = onDrag;

    useEffect(() => {
        const el = handleRef.current;
        if (!el) return;

        let dragging = false;

        const onMouseMove = (e) => {
            if (!dragging) return;
            const parent = el.parentElement;
            if (!parent) return;
            const rect = parent.getBoundingClientRect();
            const pct = ((e.clientX - rect.left) / rect.width) * 100;
            onDragRef.current(Math.max(20, Math.min(80, pct)));
        };

        const onMouseUp = () => {
            dragging = false;
            document.body.style.userSelect = '';
            el.classList.remove(styles.dragging);
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
        };

        const onMouseDown = (e) => {
            e.preventDefault();
            dragging = true;
            document.body.style.userSelect = 'none';
            el.classList.add(styles.dragging);
            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        };

        el.addEventListener('mousedown', onMouseDown);

        return () => {
            el.removeEventListener('mousedown', onMouseDown);
            if (dragging) {
                document.body.style.userSelect = '';
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
            }
        };
    }, []);

    return (
        <div
            ref={handleRef}
            className={styles.splitHandle}
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize panels"
        />
    );
}
