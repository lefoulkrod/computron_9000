import styles from './StarterPrompts.module.css';

const PROMPTS = [
    {
        icon: '🔍',
        title: 'Research a topic',
        text: 'Do a deep research on the latest developments in large language models',
    },
    {
        icon: '💻',
        title: 'Write some code',
        text: 'Write an HTML snake game',
    },
    {
        icon: '🌐',
        title: 'Browse the web',
        text: 'Go to wikipedia.org and summarize the featured article of the day',
    },
    {
        icon: '🖥️',
        title: 'Use the computer',
        text: 'Open a terminal and show me what OS is running on this machine',
    },
];

export default function StarterPrompts({ onSelect }) {
    return (
        <div className={styles.container}>
            <h2 className={styles.heading}>What can I help you with?</h2>
            <div className={styles.grid}>
                {PROMPTS.map((prompt) => (
                    <button
                        key={prompt.title}
                        className={styles.card}
                        onClick={() => onSelect(prompt.text)}
                    >
                        <span className={styles.icon}>{prompt.icon}</span>
                        <span className={styles.title}>{prompt.title}</span>
                        <span className={styles.text}>{prompt.text}</span>
                    </button>
                ))}
            </div>
        </div>
    );
}
