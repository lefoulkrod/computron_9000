import { useCallback, useEffect, useRef } from 'react';
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
    const isDraggingRef = useRef(false);

    /**
     * Handles mouse movement during drag.
     * Calculates percentage based on parent element width.
     */
    const handleMouseMove = useCallback((moveEvent) => {
        if (!handleRef.current) return;
        const parent = handleRef.current.parentElement;
        if (!parent) return;

        const rect = parent.getBoundingClientRect();
        const x = moveEvent.clientX - rect.left;
        const percentage = (x / rect.width) * 100;
        // Clamp between 20% and 80%
        const clamped = Math.max(20, Math.min(80, percentage));
        onDrag(clamped);
    }, [onDrag]);

    /**
     * Handles end of drag operation.
     * Removes listeners and dragging class.
     */
    const handleMouseUp = useCallback(() => {
        isDraggingRef.current = false;
        document.body.style.userSelect = '';
        if (handleRef.current) {
            handleRef.current.classList.remove(styles.dragging);
        }
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
    }, [handleMouseMove]);

    /**
     * Handles the start of a drag operation.
     * Attaches mousemove and mouseup listeners to document.
     *
     * @param {MouseEvent} e
     */
    const handleMouseDown = useCallback((e) => {
        e.preventDefault();
        if (!handleRef.current) return;

        isDraggingRef.current = true;
        document.body.style.userSelect = 'none';
        handleRef.current.classList.add(styles.dragging);

        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
    }, [handleMouseMove, handleMouseUp]);

    // Clean up listeners on unmount
    useEffect(() => {
        return () => {
            if (isDraggingRef.current) {
                document.body.style.userSelect = '';
                document.removeEventListener('mousemove', handleMouseMove);
                document.removeEventListener('mouseup', handleMouseUp);
            }
        };
    }, [handleMouseMove, handleMouseUp]);

    return (
        <div
            ref={handleRef}
            className={styles.splitHandle}
            onMouseDown={handleMouseDown}
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize panels"
        />
    );
}
