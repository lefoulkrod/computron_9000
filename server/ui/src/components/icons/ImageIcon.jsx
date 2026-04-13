export default function ImageIcon({ size = 14, className }) {
    return (
        <svg
            width={size}
            height={size}
            viewBox="0 0 16 16"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className={className}
            aria-hidden="true"
        >
            <rect x="1" y="2" width="14" height="12" rx="1" stroke="currentColor" strokeWidth="1.2"/>
            <circle cx="5" cy="6" r="1.5" fill="currentColor"/>
            <path d="M1 12l4-4 3 3 3-3 4 4" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/>
        </svg>
    );
}
