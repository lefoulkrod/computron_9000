import { useState, useEffect, useCallback } from 'react';
import styles from './SystemSettings.module.css';
import PackageIcon from './icons/PackageIcon';
import EyeIcon from './icons/EyeIcon';
import CompactionIcon from './icons/CompactionIcon';
import WrenchIcon from './icons/WrenchIcon';

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
                headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
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
            await fetch('/api/models/refresh', { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
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
                    <PackageIcon />
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
                        <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                </select>
            </div>


            {/* Vision Model */}
            <div className={styles.sectionLabel}>Vision</div>

            <div className={styles.settingRow}>
                <div className={styles.settingIcon}>
                    <EyeIcon size={16} />
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
            <div className={styles.note}>
                Vision was tested with Qwen3.5.
            </div>
            {/* Compaction Model */}
            <div className={styles.sectionLabel}>Compaction</div>

            <div className={styles.settingRow}>
                <div className={styles.settingIcon}>
                    <CompactionIcon />
                </div>
                <div className={styles.settingInfo}>
                    <span className={styles.settingTitle}>Compaction Model</span>
                    <span className={styles.settingDesc}>Summarizes conversation history when context fills up.</span>
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
                Compaction was fine-tuned to work with kimi-k2.5 — using a different model may produce lower quality summaries.
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
                    <WrenchIcon size={16} />
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
