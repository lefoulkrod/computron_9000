import React from 'react';
import styles from './Header.module.css';
import ThemeIcon from './icons/ThemeIcon.jsx';
import PlusIcon from './icons/PlusIcon.jsx';
import LayersIcon from './icons/LayersIcon.jsx';

export default function Header({ dark, onToggleTheme, onNewSession, showSubAgents, onToggleSubAgents }) {
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
          onClick={onToggleSubAgents}
          id="subAgentsToggle"
          className={`${styles.iconButton} ${showSubAgents ? styles.active : ''}`}
          aria-label={showSubAgents ? 'Hide sub-agents' : 'Show sub-agents'}
          title={showSubAgents ? 'Hide sub-agents' : 'Show sub-agents'}
        >
          <LayersIcon size={20} active={showSubAgents} />
        </button>
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
