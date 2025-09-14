import React from 'react';

export default function LightbulbIcon({ size = 18 }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ display: 'block' }}
    >
      <path d="M9 18h6v2a3 3 0 0 1-6 0v-2z" />
      <path d="M12 2a7 7 0 0 0-7 7c0 3 2 5 4 6v2h6v-2c2-1 4-3 4-6a7 7 0 0 0-7-7z" />
    </svg>
  );
}
