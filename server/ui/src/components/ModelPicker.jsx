import { useState, useMemo, useRef, useEffect } from 'react';
import styles from './ModelPicker.module.css';

export default function ModelPicker({ models, selected, onSelect, placeholder = 'Search or paste model name…' }) {
    const [query, setQuery] = useState('');
    const inputRef = useRef(null);

    const filtered = useMemo(() => {
        if (!query) return models || [];
        const q = query.toLowerCase();
        return (models || []).filter((m) => m.name.toLowerCase().includes(q));
    }, [models, query]);

    useEffect(() => {
        if (selected) setQuery('');
    }, [selected]);

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && query.trim()) {
            e.preventDefault();
            const exact = (models || []).find((m) => m.name === query.trim());
            if (exact) {
                onSelect(exact.name);
            } else if (filtered.length === 1) {
                onSelect(filtered[0].name);
            } else {
                onSelect(query.trim());
            }
        }
    };

    return (
        <div className={styles.picker}>
            <input
                ref={inputRef}
                type="text"
                className={styles.searchInput}
                placeholder={placeholder}
                value={selected || query}
                onChange={(e) => {
                    if (selected) onSelect(null);
                    setQuery(e.target.value);
                }}
                onFocus={() => { if (selected) { onSelect(null); setQuery(''); } }}
                onKeyDown={handleKeyDown}
            />
            {!selected && (
                <div className={styles.list}>
                    {filtered.length === 0 && query && (
                        <div className={styles.empty}>
                            No matches — press Enter to use "{query}" directly
                        </div>
                    )}
                    {filtered.map((m) => (
                        <button
                            key={m.name}
                            type="button"
                            className={styles.item}
                            onClick={() => onSelect(m.name)}
                        >
                            <span className={styles.itemName}>{m.name}</span>
                            {m.parameter_size && (
                                <span className={styles.badge}>{m.parameter_size}</span>
                            )}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}
