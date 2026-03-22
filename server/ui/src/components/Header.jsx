import React from 'react';
import styles from './Header.module.css';
import ThemeIcon from './icons/ThemeIcon.jsx';
import PlusIcon from './icons/PlusIcon.jsx';
import AudioIndicator from './AudioIndicator.jsx';

const DesktopIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
    <line x1="8" y1="21" x2="16" y2="21" />
    <line x1="12" y1="17" x2="12" y2="21" />
  </svg>
);

export default function Header({ dark, onToggleTheme, onNewConversation, audio, muted, onToggleMute, onAudioEnded, compact, onOpenSettings, onOpenDesktop }) {
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
        <div className={styles.actions}>
          <AudioIndicator
            audio={audio}
            muted={muted}
            onToggleMute={onToggleMute}
            onEnded={onAudioEnded}
          />
          {onOpenDesktop && (
            <button
              onClick={onOpenDesktop}
              className={styles.iconButton}
              aria-label="Open desktop"
              title="Open desktop"
            >
              <DesktopIcon />
            </button>
          )}
          <button
            onClick={onToggleTheme}
            className={styles.iconButton}
            aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
            title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            <ThemeIcon dark={dark} />
          </button>
          <button
            onClick={onNewConversation}
            className={styles.iconButton}
            aria-label="New conversation"
            title="New conversation"
          >
            <PlusIcon />
          </button>
          {compact && onOpenSettings && (
            <button
              onClick={onOpenSettings}
              className={styles.iconButton}
              aria-label="Settings"
              title="Settings"
            >
              <i className="bi bi-gear" style={{ fontSize: '14px' }} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
