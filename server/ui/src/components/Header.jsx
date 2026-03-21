import React from 'react';
import styles from './Header.module.css';
import ThemeIcon from './icons/ThemeIcon.jsx';
import PlusIcon from './icons/PlusIcon.jsx';
import LayersIcon from './icons/LayersIcon.jsx';
import AudioIndicator from './AudioIndicator.jsx';

const DesktopIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
    <line x1="8" y1="21" x2="16" y2="21" />
    <line x1="12" y1="17" x2="12" y2="21" />
  </svg>
);

export default function Header({ dark, onToggleTheme, onNewConversation, showSubAgents, onToggleSubAgents, audio, muted, onToggleMute, onAudioEnded, compact, onOpenSettings, onOpenDesktop }) {
  return (
    <div className={styles.header}>
      <div className={styles.headerInner}>
        {!compact && (
          <>
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
          </>
        )}
        <div className={styles.appTitle}>COMPUTRON_9000</div>
        {!compact && (
          <>
            <AudioIndicator
              audio={audio}
              muted={muted}
              onToggleMute={onToggleMute}
              onEnded={onAudioEnded}
            />
            {onOpenDesktop && (
              <button
                onClick={onOpenDesktop}
                className={`${styles.iconButton} ${styles.desktopBtn}`}
                aria-label="Open desktop"
                title="Open desktop"
              >
                <DesktopIcon />
              </button>
            )}
            <button
              onClick={onToggleSubAgents}
              id="subAgentsToggle"
              className={`${styles.iconButton} ${showSubAgents ? styles.active : ''}`}
              aria-label={showSubAgents ? 'Hide sub-agents' : 'Show sub-agents'}
              title={showSubAgents ? 'Hide sub-agents' : 'Show sub-agents'}
            >
              <LayersIcon size={20} active={showSubAgents} />
            </button>
          </>
        )}
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
          onClick={onNewConversation}
          id="newConversationBtn"
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
            <i className="bi bi-gear" style={{ fontSize: '16px' }} />
          </button>
        )}
      </div>
    </div>
  );
}
