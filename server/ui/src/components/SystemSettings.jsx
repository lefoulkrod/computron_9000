import { useState, useEffect, useCallback } from 'react';
import styles from './SystemSettings.module.css';

export default function SystemSettings({ onRunWizard }) {
    const [allModels, setAllModels] = useState([]);
    const [visionModels, setVisionModels] = useState([]);
    const [profiles, setProfiles] = useState([]);
    const [settings, setSettings] = useState({ default_agent: 'computron', vision_model: '' });
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);

    const fetchModels = useCallback(async () => {
        try {
            const [allRes, visionRes] = await Promise.all([
                fetch('/api/models'),
                fetch('/api/models?capability=vision'),
            ]);
            const allData = await allRes.json();
            const visionData = await visionRes.json();
            setAllModels(allData.models || []);
            setVisionModels(visionData.models || []);
        } catch {
            // keep existing state on error
        }
    }, []);

    useEffect(() => {
        async function init() {
            try {
                const [allRes, visionRes, settingsRes, profilesRes] = await Promise.all([
                    fetch('/api/models'),
                    fetch('/api/models?capability=vision'),
                    fetch('/api/settings'),
                    fetch('/api/profiles'),
                ]);
                const allData = await allRes.json();
                const visionData = await visionRes.json();
                const settingsData = await settingsRes.json();
                const profilesData = await profilesRes.json();
                setAllModels(allData.models || []);
                setVisionModels(visionData.models || []);
                setSettings(settingsData);
                setProfiles(profilesData);
            } catch {
                // keep defaults on error
            } finally {
                setLoading(false);
            }
        }
        init();
    }, []);

    const updateSetting = useCallback(async (key, value) => {
        setSettings((prev) => ({ ...prev, [key]: value }));
        try {
            const res = await fetch('/api/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ [key]: value }),
            });
            if (res.ok) {
                const updated = await res.json();
                setSettings(updated);
            }
        } catch {
            // silent
        }
    }, []);

    const handleRefresh = useCallback(async () => {
        setRefreshing(true);
        try {
            await fetch('/api/models/refresh', { method: 'POST' });
            await fetchModels();
        } catch {
            // silent
        } finally {
            setRefreshing(false);
        }
    }, [fetchModels]);

    const connected = allModels.length > 0;

    if (loading) return null;

    return (
        <div className={styles.container}>
            {/* Default Agent */}
            <div className={styles.sectionLabel}>Default Agent</div>

            <div className={styles.settingRow}>
                <div className={styles.settingIcon}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                        <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
                        <line x1="12" y1="22.08" x2="12" y2="12" />
                    </svg>
                </div>
                <div className={styles.settingInfo}>
                    <span className={styles.settingTitle}>Default Agent</span>
                    <span className={styles.settingDesc}>The agent profile used as the system agent.</span>
                </div>
                <select
                    className={styles.select}
                    value={settings.default_agent || 'computron'}
                    onChange={(e) => updateSetting('default_agent', e.target.value)}
                >
                    {profiles.map((p) => (
                        <option key={p.id} value={p.id}>{p.icon} {p.name}</option>
                    ))}
                </select>
            </div>

            <div className={styles.note}>
                The default agent is used for background tasks and as the fallback.
                You can select a different profile per conversation from the chat input.
            </div>

            {/* Vision Model */}
            <div className={styles.sectionLabel}>Vision</div>

            <div className={styles.settingRow}>
                <div className={styles.settingIcon}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                        <circle cx="12" cy="12" r="3" />
                    </svg>
                </div>
                <div className={styles.settingInfo}>
                    <span className={styles.settingTitle}>Vision Model</span>
                    <span className={styles.settingDesc}>Used for image descriptions and screenshot analysis. Only models with vision capability are shown.</span>
                </div>
                <select
                    className={styles.select}
                    value={settings.vision_model}
                    onChange={(e) => updateSetting('vision_model', e.target.value)}
                >
                    <option value="">Select a model</option>
                    {visionModels.map((m) => (
                        <option key={m.name} value={m.name}>{m.name}</option>
                    ))}
                </select>
            </div>

            {/* Compaction Model */}
            <div className={styles.sectionLabel}>Compaction</div>

            <div className={styles.settingRow}>
                <div className={styles.settingIcon}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="4 14 10 14 10 20" />
                        <polyline points="20 10 14 10 14 4" />
                        <line x1="14" y1="10" x2="21" y2="3" />
                        <line x1="3" y1="21" x2="10" y2="14" />
                    </svg>
                </div>
                <div className={styles.settingInfo}>
                    <span className={styles.settingTitle}>Compaction Model</span>
                    <span className={styles.settingDesc}>Summarizes conversation history when context fills up. Fine-tuned to work with kimi-k2.5.</span>
                </div>
                <select
                    className={styles.select}
                    value={settings.compaction_model || ''}
                    onChange={(e) => updateSetting('compaction_model', e.target.value)}
                >
                    <option value="">Select a model</option>
                    {allModels.map((m) => (
                        <option key={m.name} value={m.name}>{m.name}</option>
                    ))}
                </select>
            </div>

            <div className={styles.note}>
                Defaults to the main model selected during setup. Compaction was fine-tuned
                to work with kimi-k2.5 — using a different model may produce lower quality summaries.
            </div>

            {/* Ollama Connection */}
            <div className={styles.sectionLabel}>Ollama Connection</div>

            <div className={styles.settingRow}>
                <div className={styles.settingIcon}>
                    <span className={`${styles.statusDot} ${connected ? styles.statusConnected : styles.statusDisconnected}`} />
                </div>
                <div className={styles.settingInfo}>
                    <span className={styles.settingTitle}>
                        {connected ? 'Connected' : 'Disconnected'}
                    </span>
                    <span className={styles.settingDesc}>
                        {connected
                            ? `${allModels.length} model${allModels.length === 1 ? '' : 's'} available`
                            : 'Unable to reach Ollama'}
                    </span>
                </div>
                <button
                    className={styles.actionBtn}
                    onClick={handleRefresh}
                    disabled={refreshing}
                >
                    {refreshing ? 'Refreshing...' : 'Refresh'}
                </button>
            </div>

            {/* Setup */}
            <div className={styles.sectionLabel}>Setup</div>

            <div className={styles.settingRow}>
                <div className={styles.settingIcon}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
                    </svg>
                </div>
                <div className={styles.settingInfo}>
                    <span className={styles.settingTitle}>Setup Wizard</span>
                    <span className={styles.settingDesc}>Re-run the initial configuration wizard</span>
                </div>
                <button
                    className={styles.actionBtn}
                    onClick={onRunWizard}
                >
                    Run Setup Wizard
                </button>
            </div>
        </div>
    );
}
