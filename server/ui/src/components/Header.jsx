import React from 'react';
import styles from './Header.module.css';
import ThemeIcon from './icons/ThemeIcon.jsx';
import AudioIndicator from './AudioIndicator.jsx';

export default function Header({ dark, onToggleTheme, onNewConversation, audio, muted, onToggleMute, onAudioEnded, desktopEnabled, onOpenDesktop }) {
  return (
    <div className={styles.header}>
      <div className={styles.headerInner}>
        <div className={styles.appTitle}>COMPUTRON</div>
        <div className={styles.actions}>
          <AudioIndicator
            audio={audio}
            muted={muted}
            onToggleMute={onToggleMute}
            onEnded={onAudioEnded}
          />
          {desktopEnabled && (
            <button
              onClick={onOpenDesktop}
              className={styles.iconButton}
              aria-label="Open desktop"
              title="Open desktop"
            >
              <i className="bi bi-display" />
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
            <i className="bi bi-plus-lg" />
          </button>
        </div>
      </div>
    </div>
  );
}
