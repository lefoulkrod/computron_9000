import { useState, useEffect } from 'react';
import styles from './ProfileSelector.module.css';

export default function ProfileSelector({ selectedId, onChange, disabled, refreshSignal }) {
    const [profiles, setProfiles] = useState([]);

    useEffect(() => {
        let cancelled = false;
        fetch('/api/profiles')
            .then((res) => res.json())
            .then((data) => {
                if (!cancelled) setProfiles(data);
            })
            .catch(() => {});
        return () => { cancelled = true; };
    }, [refreshSignal]);

    if (profiles.length === 0) return null;

    return (
        <select
            className={styles.select}
            value={selectedId}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            aria-label="Agent profile"
        >
            {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                    {p.name}
                </option>
            ))}
        </select>
    );
}
