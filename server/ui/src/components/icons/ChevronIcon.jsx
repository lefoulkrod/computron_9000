import React from 'react';

export default function ChevronIcon({ size = 12, direction = 'down' }) {
    const isDown = direction === 'down';
    return (
        <svg width={size} height={size} viewBox="0 0 12 12" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
            <path
                d={isDown ? "M2 4l4 4 4-4" : "M2 8l4-4 4 4"}
                stroke="currentColor"
                strokeWidth="2"
                fill="none"
                strokeLinecap="round"
                strokeLinejoin="round"
            />
        </svg>
    );
}
