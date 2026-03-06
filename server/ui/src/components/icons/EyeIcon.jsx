export default function EyeIcon({ size = 14, className, slashed = false }) {
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
                d="M1 8C1 8 3.5 3 8 3C12.5 3 15 8 15 8C15 8 12.5 13 8 13C3.5 13 1 8 1 8Z"
                stroke="currentColor"
                strokeWidth="1.2"
                strokeLinejoin="round"
            />
            <circle cx="8" cy="8" r="2" fill="currentColor" />
            {slashed && (
                <line
                    x1="2.5"
                    y1="2.5"
                    x2="13.5"
                    y2="13.5"
                    stroke="currentColor"
                    strokeWidth="1.4"
                    strokeLinecap="round"
                />
            )}
        </svg>
    );
}
