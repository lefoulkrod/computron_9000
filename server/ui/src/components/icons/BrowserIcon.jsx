import React from 'react';

export default function BrowserIcon({ size = 16 }) {
    return (
        <svg width={size} height={size} viewBox="0 0 16 16" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
            <path d="M0 2a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V2zm2-1a1 1 0 0 0-1 1v1h14V2a1 1 0 0 0-1-1H2zM1 5v9a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V5H1z" />
        </svg>
    );
}
