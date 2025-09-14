import React from 'react';
import styles from './Header.module.css';
import ThemeIcon from './icons/ThemeIcon.jsx';
import PlusIcon from './icons/PlusIcon.jsx';

export default function Header({ dark, onToggleTheme, onNewSession }) {
  return (
    <div className={styles.header}>
      <div className={styles.headerInner}>
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
        <button
          onClick={onToggleTheme}
          id="themeToggle"
          className={styles.iconButton}
          aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
          title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          <ThemeIcon dark={dark} />
        </button>
        <button
          onClick={onNewSession}
          id="newSessionBtn"
          className={styles.iconButton}
          aria-label="New session"
          title="New session"
        >
          <PlusIcon />
        </button>
      </div>
    </div>
  );
}
