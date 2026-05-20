import React from 'react';
import styles from './Header.module.css';
import AudioIndicator from './AudioIndicator.jsx';

export default function Header({ audio, muted, onToggleMute, onAudioEnded, desktopEnabled, onOpenDesktop }) {
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
        </div>
      </div>
    </div>
  );
}
