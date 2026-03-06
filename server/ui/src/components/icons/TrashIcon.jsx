export default function TrashIcon({ size = 14, className }) {
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
            <path
                d="M6 2h4a1 1 0 0 1 1 1v1H5V3a1 1 0 0 1 1-1Z"
                fill="currentColor"
                opacity="0.7"
            />
            <rect x="2" y="4" width="12" height="1.2" rx="0.6" fill="currentColor" />
            <path
                d="M3.5 6l.8 7.2A1 1 0 0 0 5.3 14h5.4a1 1 0 0 0 1-.8L12.5 6H3.5Zm3 1h1v5.5H6.5V7Zm2 0h1v5.5H8.5V7Z"
                fill="currentColor"
            />
        </svg>
    );
}
