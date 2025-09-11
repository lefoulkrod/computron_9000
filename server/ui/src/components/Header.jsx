import React from 'react';

export default function Header({ dark, onToggleTheme, onNewSession }) {
  return (
    <div className="header">
      <img src="/static/computron_logo.png" alt="Computron Logo" className="logo logo-light" />
      <img src="/static/computron_logo_dark.png" alt="Computron Logo Dark" className="logo logo-dark" />
      <div className="app-title">COMPUTRON_9000</div>
      <button onClick={onToggleTheme} id="themeToggle">
        <i className="bi bi-lamp"></i> {dark ? 'Light' : 'Dark'}
      </button>
      <button onClick={onNewSession} id="newSessionBtn">
        <i className="bi bi-plus-circle"></i> New Session
      </button>
    </div>
  );
}
