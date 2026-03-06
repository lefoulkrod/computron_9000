import styles from './AudioIndicator.module.css';

function AudioIndicator({ audio, muted, onToggleMute, onEnded }) {
    if (!audio) return null;

    return (
        <>
            <audio
                key={audio.key}
                src={audio.src}
                autoPlay
                muted={muted}
                onEnded={onEnded}
            />
            <button
                className={`${styles.button} ${muted ? styles.muted : ''}`}
                onClick={onToggleMute}
                title={muted ? 'Unmute' : 'Mute'}
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
