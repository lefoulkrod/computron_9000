export default function DesktopIcon({ size = 14, className }) {
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
            <rect
                x="1.5"
                y="2.5"
                width="13"
                height="9"
                rx="1"
                stroke="currentColor"
                strokeWidth="1.2"
            />
            <path
                d="M6.5 14.5h3M8 11.5v3"
                stroke="currentColor"
                strokeWidth="1.2"
                strokeLinecap="round"
            />
        </svg>
    );
}
