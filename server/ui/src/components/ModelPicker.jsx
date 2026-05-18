import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import styles from './ModelPicker.module.css';

// Module-level cache: provider name → models array.
// Shared across every ModelPicker instance so switching tabs and
// switching pages doesn't re-fetch lists we've already seen.
const _modelsCache = new Map();
// In-flight fetches per provider — dedupes concurrent requests.
const _inFlight = new Map();

async function _fetchModels(provider) {
    if (_modelsCache.has(provider)) return _modelsCache.get(provider);
    if (_inFlight.has(provider)) return _inFlight.get(provider);
    const p = fetch(`/api/models?provider=${encodeURIComponent(provider)}`)
        .then((r) => r.json().then((data) => ({ ok: r.ok, status: r.status, data })))
        .then(({ ok, data }) => {
            if (!ok) throw new Error(data?.message || data?.error || 'Failed to load models');
            const models = data.models || [];
            _modelsCache.set(provider, models);
            _inFlight.delete(provider);
            return models;
        })
        .catch((err) => {
            _inFlight.delete(provider);
            throw err;
        });
    _inFlight.set(provider, p);
    return p;
}

/** Drop a provider's cached model list (or all of them) so the next fetch re-queries. */
export function invalidateModelCache(provider) {
    if (provider) _modelsCache.delete(provider);
    else _modelsCache.clear();
}

function _formatCtx(tokens) {
    if (tokens == null) return null;
    if (tokens >= 1_000_000) return `${Math.round(tokens / 1_000_000 * 10) / 10}M`;
    if (tokens >= 1_000) return `${Math.round(tokens / 1_000)}K`;
    return String(tokens);
}

/**
 * Provider-aware model picker.
 *
 * Closed state: a select-styled trigger showing `provider / model-name`
 * (or "Choose a model…" when nothing's set).
 *
 * Open state: a popover anchored to the trigger, with a provider tab bar
 * across the top (one tab per configured provider; hidden when there's
 * only one), a search box, and the active provider's model list.
 *
 * Props:
 *  - providers: array of { name, label? } — the configured providers (from
 *    GET /api/providers). Empty array → trigger is disabled.
 *  - selectedProvider: currently chosen provider name (or null/"" when unset).
 *  - selectedModel: currently chosen model name (or null/"" when unset).
 *  - onSelect: (provider, model) => void. Called when the user picks a row.
 *  - placeholder: trigger text when nothing is selected. Default "Choose a model…".
 *  - capability: optional filter — "vision" hides models without supports_images.
 */
export default function ModelPicker({
    providers,
    selectedProvider,
    selectedModel,
    onSelect,
    placeholder = 'Choose a model…',
    capability,
    defaultOpen = false,
}) {
    const provs = providers || [];
    const showTabs = provs.length > 1;

    // The tab the user is currently looking at inside the popover.
    // Defaults to the selected provider (if any), else the first one.
    const initialTab = selectedProvider || provs[0]?.name || '';
    const [open, setOpen] = useState(defaultOpen);
    const [activeTab, setActiveTab] = useState(initialTab);
    const [query, setQuery] = useState('');
    const [models, setModels] = useState(() => _modelsCache.get(initialTab) || []);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const wrapperRef = useRef(null);
    const searchRef = useRef(null);

    // Re-sync active tab when the parent's selection changes (e.g. a different
    // profile is loaded into ProfileBuilder).
    useEffect(() => {
        if (!open && selectedProvider) setActiveTab(selectedProvider);
    }, [selectedProvider, open]);

    // Fetch models for the active tab whenever it changes (or the popover opens).
    useEffect(() => {
        if (!open || !activeTab) return;
        const cached = _modelsCache.get(activeTab);
        if (cached) {
            setModels(cached);
            setLoading(false);
            setError(null);
            return;
        }
        let cancelled = false;
        setLoading(true);
        setError(null);
        _fetchModels(activeTab)
            .then((m) => { if (!cancelled) { setModels(m); setLoading(false); } })
            .catch((err) => { if (!cancelled) { setError(err.message || 'error'); setLoading(false); } });
        return () => { cancelled = true; };
    }, [activeTab, open]);

    // Close on click-outside / escape.
    useEffect(() => {
        if (!open) return;
        const onDown = (e) => {
            if (wrapperRef.current && !wrapperRef.current.contains(e.target)) setOpen(false);
        };
        const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
        document.addEventListener('mousedown', onDown);
        document.addEventListener('keydown', onKey);
        return () => {
            document.removeEventListener('mousedown', onDown);
            document.removeEventListener('keydown', onKey);
        };
    }, [open]);

    // Focus the search input on open.
    useEffect(() => {
        if (open && searchRef.current) searchRef.current.focus();
    }, [open]);

    // Filter the active tab's models by query + optional capability.
    const filtered = useMemo(() => {
        let list = models;
        if (capability === 'vision') list = list.filter((m) => m.supports_images);
        if (query) {
            const q = query.toLowerCase();
            list = list.filter((m) => m.name.toLowerCase().includes(q));
        }
        return list;
    }, [models, query, capability]);

    const handleOpenToggle = useCallback(() => {
        if (!provs.length) return;
        setOpen((v) => {
            if (!v) {
                // Re-pin to the selected provider every time we open.
                setActiveTab(selectedProvider || provs[0].name);
                setQuery('');
            }
            return !v;
        });
    }, [provs, selectedProvider]);

    const handlePick = useCallback((model) => {
        // Pass through the full ModelInfo so parents can read context_window,
        // parameter_size, capabilities, etc. without re-fetching.
        onSelect?.(activeTab, model.name, model);
        setOpen(false);
    }, [onSelect, activeTab]);

    const triggerLabel = (() => {
        if (selectedModel) return null; // structured render below
        if (!provs.length) return 'No providers configured';
        return placeholder;
    })();

    return (
        <div className={styles.wrapper} ref={wrapperRef} data-testid="model-picker">
            <button
                type="button"
                className={`${styles.trigger} ${open ? styles.triggerOpen : ''} ${selectedModel ? '' : styles.triggerEmpty}`}
                onClick={handleOpenToggle}
                disabled={!provs.length}
                aria-haspopup="listbox"
                aria-expanded={open}
                data-testid="model-picker-trigger"
                data-selected-provider={selectedProvider || ''}
                data-selected-model={selectedModel || ''}
            >
                {selectedModel ? (
                    <>
                        {selectedProvider && (
                            <>
                                <span className={styles.triggerProv}>{selectedProvider}</span>
                                <span className={styles.triggerSep}>/</span>
                            </>
                        )}
                        <span className={styles.triggerModel}>{selectedModel}</span>
                    </>
                ) : (
                    <span className={styles.triggerPlaceholder}>{triggerLabel}</span>
                )}
                <span className={styles.triggerCaret} aria-hidden="true">▾</span>
            </button>

            {open && (
                <div className={styles.popover} role="listbox" data-testid="model-picker-popover">
                    {showTabs && (
                        <div className={styles.tabs} role="tablist">
                            {provs.map((p) => (
                                <button
                                    key={p.name}
                                    type="button"
                                    role="tab"
                                    aria-selected={activeTab === p.name}
                                    className={`${styles.tab} ${activeTab === p.name ? styles.tabActive : ''}`}
                                    onClick={() => { setActiveTab(p.name); setQuery(''); }}
                                    data-testid={`model-picker-tab-${p.name}`}
                                >
                                    {p.label || p.name}
                                </button>
                            ))}
                        </div>
                    )}

                    <div className={styles.search}>
                        <input
                            ref={searchRef}
                            type="text"
                            className={styles.searchInput}
                            placeholder={`Search ${activeTab} models…`}
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                        />
                    </div>

                    <div className={styles.list}>
                        {loading && <div className={styles.empty}>Loading…</div>}
                        {error && !loading && (
                            <div className={styles.empty}>Couldn't load models — {error}</div>
                        )}
                        {!loading && !error && filtered.length === 0 && (
                            <div className={styles.empty}>
                                {query ? `No matches for "${query}"` : 'No models available'}
                            </div>
                        )}
                        {!loading && !error && filtered.map((m) => {
                            const ctx = _formatCtx(m.context_window);
                            const isSelected = m.name === selectedModel && activeTab === selectedProvider;
                            return (
                                <button
                                    key={m.name}
                                    type="button"
                                    className={`${styles.item} ${isSelected ? styles.itemSelected : ''}`}
                                    onClick={() => handlePick(m)}
                                    data-testid="model-item"
                                    data-model-name={m.name}
                                >
                                    <span className={styles.itemName}>{m.name}</span>
                                    <span className={styles.badges}>
                                        {m.supports_thinking && <span className={styles.capBadge}>think</span>}
                                        {m.supports_images && <span className={styles.capBadge}>vision</span>}
                                        {ctx && <span className={styles.badge}>{ctx}</span>}
                                        {m.parameter_size && <span className={styles.badge}>{m.parameter_size}</span>}
                                    </span>
                                </button>
                            );
                        })}
                    </div>
                </div>
            )}
        </div>
    );
}
