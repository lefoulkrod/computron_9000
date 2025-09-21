import React, { createContext, useCallback, useContext, useRef, useState, useEffect } from 'react';
import styles from './Toasts.module.css';

// Context shape
const ToastContext = createContext(null);

export function ToastProvider({ children }) {
    const [toasts, setToasts] = useState([]); // { id, message, type }
    const timersRef = useRef(new Map());

    const removeToast = useCallback((id) => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
        const timer = timersRef.current.get(id);
        if (timer) {
            clearTimeout(timer);
            timersRef.current.delete(id);
        }
    }, []);

    const addToast = useCallback((message, options = {}) => {
        const { type = 'error', duration = 5000, id: providedId } = options;
        const id = providedId || `${Date.now()}_${Math.random().toString(36).slice(2)}`;
        setToasts((prev) => [...prev, { id, message, type }]);
        if (duration !== Infinity) {
            const timer = setTimeout(() => removeToast(id), duration);
            timersRef.current.set(id, timer);
        }
        return id;
    }, [removeToast]);

    // Cleanup timers on unmount
    useEffect(() => () => {
        timersRef.current.forEach((t) => clearTimeout(t));
        timersRef.current.clear();
    }, []);

    const contextValue = {
        addToast,
        removeToast,
    };

    return (
        <ToastContext.Provider value={contextValue}>
            {children}
            <div className={styles.toastViewport} role="region" aria-live="polite" aria-label="Notifications">
                {toasts.map((t) => (
                    <div key={t.id} className={`${styles.toast} ${styles[t.type] || styles.info}`}>
                        <div className={styles.message}>{t.message}</div>
                        <button
                            type="button"
                            aria-label="Dismiss notification"
                            className={styles.close}
                            onClick={() => removeToast(t.id)}
                        >
                            ×
                        </button>
                    </div>
                ))}
            </div>
        </ToastContext.Provider>
    );
}

export function useToast() {
    const ctx = useContext(ToastContext);
    if (!ctx) {
        throw new Error('useToast must be used within a ToastProvider');
    }
    return ctx;
}

export default ToastProvider;
