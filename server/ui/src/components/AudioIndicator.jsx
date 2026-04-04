import { useRef, useState, useEffect } from 'react';
import styles from './AudioIndicator.module.css';

function AudioIndicator({ audio, muted, onToggleMute, onEnded }) {
    const audioRef = useRef(null);
    const [paused, setPaused] = useState(false);

    // Reset paused state when a new audio source is loaded
    useEffect(() => {
        setPaused(false);
    }, [audio?.key]);

    if (!audio) return null;

    const handleToggle = () => {
        const el = audioRef.current;
        if (!el) return;
        if (el.paused) {
            el.play();
            setPaused(false);
        } else {
            el.pause();
            setPaused(true);
        }
    };

    return (
        <>
            <audio
                ref={audioRef}
                key={audio.key}
                src={audio.src}
                autoPlay
                muted={muted}
                onEnded={onEnded}
            />
            <button
                className={`${styles.button} ${paused ? styles.paused : ''}`}
                onClick={handleToggle}
                title={paused ? 'Resume' : 'Pause'}
            >
                <span className={styles.bar} />
                <span className={styles.bar} />
                <span className={styles.bar} />
                <span className={styles.bar} />
            </button>
        </>
    );
}

export default AudioIndicator;
