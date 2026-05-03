import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '../utils/api.js';
import styles from './SystemSettings.module.css';
import PackageIcon from './icons/PackageIcon';
import EyeIcon from './icons/EyeIcon';
import CompactionIcon from './icons/CompactionIcon';
import WrenchIcon from './icons/WrenchIcon';
import ToggleSwitch from './ToggleSwitch.jsx';
import Button from './primitives/Button.jsx';
import StatusDot from './StatusDot.jsx';
import ChevronRightIcon from './icons/ChevronRightIcon';

export default function SystemSettings({ onRunWizard }) {
    const [allModels, setAllModels] = useState([]);
    const [profiles, setProfiles] = useState([]);
    const [settings, setSettings] = useState({ default_agent: 'computron', vision_model: '' });
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [visionAdvancedOpen, setVisionAdvancedOpen] = useState(false);

    const visionModels = allModels.filter((m) => (m.capabilities || []).includes('vision'));

    const fetchModels = useCallback(async () => {
        try {
            const res = await fetch('/api/models');
            const data = await res.json();
            setAllModels(data.models || []);
        } catch {
            // keep existing state on error
        }
    }, []);

    useEffect(() => {
        async function init() {
            try {
                const [modelsRes, settingsRes, profilesRes] = await Promise.all([
                    fetch('/api/models'),
                    fetch('/api/settings'),
                    fetch('/api/profiles'),
                ]);
                const modelsData = await modelsRes.json();
                const settingsData = await settingsRes.json();
                const profilesData = await profilesRes.json();
                setAllModels(modelsData.models || []);
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
            const res = await apiFetch('/api/settings', {
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
            await apiFetch('/api/models/refresh', { method: 'POST' });
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


            {/* Vision */}
            <div className={styles.sectionLabel}>Vision</div>

            <div className={styles.groupCard}>
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
                        data-testid="vision-model-select"
                    >
                        <option value="">Select a model</option>
                        {visionModels.map((m) => (
                            <option key={m.name} value={m.name}>{m.name}</option>
                        ))}
                    </select>
                </div>

                <button
                    type="button"
                    className={`${styles.groupDisclosure} ${visionAdvancedOpen ? styles.groupDisclosureOpen : ''}`}
                    onClick={() => setVisionAdvancedOpen((v) => !v)}
                    aria-expanded={visionAdvancedOpen}
                    data-testid="vision-advanced-toggle"
                >
                    <ChevronRightIcon className={styles.chev} />
                    Advanced inference
                </button>

                {visionAdvancedOpen && (
                    <div className={styles.groupBody} data-testid="vision-advanced-panel">
                        <label className={styles.groupRow} data-testid="vision-think-toggle">
                            <div className={styles.settingInfo}>
                                <span className={styles.settingTitle}>Thinking</span>
                                <span className={styles.settingDesc}>Step-by-step reasoning before answering. Slower but more accurate.</span>
                            </div>
                            <ToggleSwitch
                                checked={!!settings.vision_think}
                                onChange={(e) => updateSetting('vision_think', e.target.checked)}
                                aria-label="Thinking"
                            />
                        </label>
                        {[
                            { key: 'temperature', label: 'Temperature', desc: '0.0 = deterministic, 0.7 = general, 1.0+ = creative.', step: 0.1 },
                            { key: 'top_k', label: 'Top K', desc: '10 = factual, 40 = general, 100+ = creative.' },
                            { key: 'num_ctx', label: 'Context (num_ctx)', desc: 'Maximum context window in tokens.' },
                            { key: 'num_predict', label: 'Max Output (num_predict)', desc: 'Tokens the model can generate per call.' },
                        ].map(({ key, label, desc, step }) => (
                            <div key={key} className={styles.groupRow}>
                                <div className={styles.settingInfo}>
                                    <span className={styles.settingTitle}>{label}</span>
                                    <span className={styles.settingDesc}>{desc}</span>
                                </div>
                                <input
                                    className={styles.numberInput}
                                    type="number"
                                    step={step ?? 1}
                                    value={settings.vision_options?.[key] ?? ''}
                                    data-testid={`vision-option-${key}`}
                                    onChange={(e) => {
                                        const raw = e.target.value;
                                        const num = raw === '' ? null : Number(raw);
                                        updateSetting('vision_options', {
                                            ...(settings.vision_options || {}),
                                            [key]: num,
                                        });
                                    }}
                                />
                            </div>
                        ))}
                    </div>
                )}
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
                <div className={styles.settingIcon} style={{ opacity: 1 }}>
                    <StatusDot status={connected ? 'connected' : 'disconnected'} />
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
                <Button
                    onClick={handleRefresh}
                    disabled={refreshing}
                >
                    {refreshing ? 'Refreshing…' : 'Refresh'}
                </Button>
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
                <Button onClick={onRunWizard}>
                    Run Setup Wizard
                </Button>
            </div>
        </div>
    );
}
