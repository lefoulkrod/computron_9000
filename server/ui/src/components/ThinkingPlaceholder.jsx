import { useState, useEffect, useRef } from 'react';
import styles from './ThinkingPlaceholder.module.css';

const _PHRASES = [
    'initializing neural pathways...',
    'crunching the numbers...',
    'consulting the oracle...',
    'warming up the circuits...',
    'scanning knowledge banks...',
    'engaging thought engines...',
    'calibrating response matrix...',
    'running inference loops...',
    'decoding your request...',
    'synthesizing a response...',
];

const _TYPE_SPEED = 35;    // ms per character typing
const _ERASE_SPEED = 20;   // ms per character erasing
const _PAUSE_AFTER = 1400; // ms to hold the full phrase
const _PAUSE_BETWEEN = 250; // ms pause between erase and next phrase

/**
 * Terminal-style typewriter placeholder that cycles through
 * phrases with a blinking cursor, like typing into a shell.
 */
export default function ThinkingPlaceholder() {
    const [text, setText] = useState('');
    const phraseIdx = useRef(Math.floor(Math.random() * _PHRASES.length));
    const charIdx = useRef(0);
    const erasing = useRef(false);

    useEffect(() => {
        let timer;
        const tick = () => {
            const phrase = _PHRASES[phraseIdx.current];
            if (!erasing.current) {
                charIdx.current++;
                setText(phrase.slice(0, charIdx.current));
                if (charIdx.current >= phrase.length) {
                    timer = setTimeout(() => {
                        erasing.current = true;
                        tick();
                    }, _PAUSE_AFTER);
                    return;
                }
                timer = setTimeout(tick, _TYPE_SPEED);
            } else {
                charIdx.current--;
                setText(phrase.slice(0, charIdx.current));
                if (charIdx.current <= 0) {
                    erasing.current = false;
                    phraseIdx.current = (phraseIdx.current + 1) % _PHRASES.length;
                    timer = setTimeout(tick, _PAUSE_BETWEEN);
                    return;
                }
                timer = setTimeout(tick, _ERASE_SPEED);
            }
        };

        timer = setTimeout(tick, _PAUSE_BETWEEN);
        return () => clearTimeout(timer);
    }, []);

    return (
        <div className={styles.container}>
            <span className={styles.text}>{text}</span>
            <span className={styles.cursor} />
        </div>
    );
}
