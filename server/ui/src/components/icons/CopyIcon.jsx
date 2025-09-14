import React from 'react';

export default function CopyIcon({ size = 16 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect x="9" y="9" width="11" height="11" rx="2" ry="2" stroke="currentColor" strokeWidth="1.8" fill="none" />
      <rect x="4" y="4" width="11" height="11" rx="2" ry="2" stroke="currentColor" strokeWidth="1.8" fill="none" />
    </svg>
  );
}

