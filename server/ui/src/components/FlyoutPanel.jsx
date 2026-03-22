import React from 'react';
import styles from './FlyoutPanel.module.css';

export default function FlyoutPanel({ title, onClose, children }) {
    return (
        <>
            <div className={styles.flyout}>
                <div className={styles.header}>
                    <span className={styles.title}>{title}</span>
                    <button className={styles.close} onClick={onClose}>&times;</button>
                </div>
                <div className={styles.body}>
                    {children}
                </div>
            </div>
            <div className={styles.scrim} onClick={onClose} />
        </>
    );
}
