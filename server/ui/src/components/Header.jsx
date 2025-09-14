import React from 'react';
import styles from './Header.module.css';

export default function Header({ dark, onToggleTheme, onNewSession }) {
  return (
    <div className={styles.header}>
      <img
        src="/static/computron_logo.png"
        alt="Computron Logo"
        className={`${styles.logo} ${styles.logoLight}`}
      />
      <img
        src="/static/computron_logo_dark.png"
        alt="Computron Logo Dark"
        className={`${styles.logo} ${styles.logoDark}`}
      />
      <div className={styles.appTitle}>COMPUTRON_9000</div>
      <button onClick={onToggleTheme} id="themeToggle">
        <i className="bi bi-lamp"></i> {dark ? 'Light' : 'Dark'}
      </button>
      <button onClick={onNewSession} id="newSessionBtn">
        <i className="bi bi-plus-circle"></i> New Session
      </button>
    </div>
  );
}
