import { useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import styles from './Lightbox.module.css';

export default function Lightbox({ src, alt, onClose }) {
    const handleKey = useCallback((e) => {
        if (e.key === 'Escape') onClose();
    }, [onClose]);

    useEffect(() => {
        document.addEventListener('keydown', handleKey);
        return () => document.removeEventListener('keydown', handleKey);
    }, [handleKey]);

    return createPortal(
        <div className={styles.overlay} onClick={onClose}>
            <img
                className={styles.img}
                src={src}
                alt={alt}
                onClick={(e) => e.stopPropagation()}
            />
        </div>,
        document.body
    );
}
