import { useState, useEffect, useCallback } from 'react';
import styles from './SystemSettings.module.css';
import ModelPicker from './ModelPicker.jsx';
import PackageIcon from './icons/PackageIcon';
import EyeIcon from './icons/EyeIcon';
import CompactionIcon from './icons/CompactionIcon';
import ToggleSwitch from './ToggleSwitch.jsx';
import ChevronRightIcon from './icons/ChevronRightIcon';

export default function SystemSettings() {
    const [providers, setProviders] = useState([]);
    const [profiles, setProfiles] = useState([]);
    const [settings, setSettings] = useState({ default_agent: 'computron' });
    const [loading, setLoading] = useState(true);
    const [visionAdvancedOpen, setVisionAdvancedOpen] = useState(false);

    useEffect(() => {
        async function init() {
            try {
                const [providersRes, settingsRes, profilesRes] = await Promise.all([
                    fetch('/api/providers'),
                    fetch('/api/settings'),
                    fetch('/api/profiles'),
                ]);
                const providersData = await providersRes.json();
                const settingsData = await settingsRes.json();
                const profilesData = await profilesRes.json();
                setProviders(providersData.providers || []);
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

    // Update a (provider, model) pair atomically so they always stay in sync.
    const updateProviderModel = useCallback(async (providerKey, modelKey, provider, model) => {
        setSettings((prev) => ({ ...prev, [providerKey]: provider || '', [modelKey]: model || '' }));
        try {
            const res = await fetch('/api/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ [providerKey]: provider || '', [modelKey]: model || '' }),
            });
            if (res.ok) {
                const updated = await res.json();
                setSettings(updated);
            }
        } catch {
            // silent
        }
    }, []);

    // The provider name driving the vision_options field-visibility logic.
    const visionProvider = settings.vision_provider || (providers[0]?.name ?? '');

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
                        <span className={styles.settingDesc}>Used for image descriptions and screenshot analysis. Choose a model that supports vision (image input).</span>
                    </div>
                </div>
                <div className={styles.pickerRow} data-testid="vision-model-picker">
                    <ModelPicker
                        providers={providers}
                        selectedProvider={settings.vision_provider || null}
                        selectedModel={settings.vision_model || null}
                        onSelect={(p, m) => updateProviderModel('vision_provider', 'vision_model', p, m)}
                        placeholder="Choose a vision model…"
                        capability="vision"
                    />
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
                            { key: 'top_k', label: 'Top K', desc: '10 = factual, 40 = general, 100+ = creative.', providers: ['ollama', 'anthropic'] },
                            { key: 'top_p', label: 'Top P', desc: '0.5 = focused, 0.9 = general, 1.0 = everything.', step: 0.05 },
                            { key: 'num_ctx', label: 'Context Window', desc: 'Maximum context window in tokens.', providers: ['ollama'] },
                            { key: 'num_predict', label: 'Max Output (num_predict)', desc: 'Tokens the model can generate per call.' },
                        ].filter(({ providers }) => !providers || providers.includes(visionProvider)).map(({ key, label, desc, step }) => (
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

            {/* Compaction */}
            <div className={styles.sectionLabel}>Compaction</div>

            <div className={styles.groupCard}>
                <div className={styles.settingRow}>
                    <div className={styles.settingIcon}>
                        <CompactionIcon />
                    </div>
                    <div className={styles.settingInfo}>
                        <span className={styles.settingTitle}>Compaction Model</span>
                        <span className={styles.settingDesc}>Summarizes conversation history when context fills up.</span>
                    </div>
                </div>
                <div className={styles.pickerRow} data-testid="compaction-model-picker">
                    <ModelPicker
                        providers={providers}
                        selectedProvider={settings.compaction_provider || null}
                        selectedModel={settings.compaction_model || null}
                        onSelect={(p, m) => updateProviderModel('compaction_provider', 'compaction_model', p, m)}
                        placeholder="Choose a compaction model…"
                    />
                </div>
            </div>

            <div className={styles.note}>
                Compaction was fine-tuned to work with kimi-k2.5 — using a different model may produce lower quality summaries.
            </div>

            {/* Title Generation */}
            <div className={styles.sectionLabel}>Title Generation</div>

            <div className={styles.groupCard}>
                <div className={styles.settingRow}>
                    <div className={styles.settingIcon}>
                        <PackageIcon />
                    </div>
                    <div className={styles.settingInfo}>
                        <span className={styles.settingTitle}>Title Model</span>
                        <span className={styles.settingDesc}>Generates a 3–5 word title for each new conversation from the first message.</span>
                    </div>
                </div>
                <div className={styles.pickerRow} data-testid="title-model-picker">
                    <ModelPicker
                        providers={providers}
                        selectedProvider={settings.title_provider || null}
                        selectedModel={settings.title_model || null}
                        onSelect={(p, m) => updateProviderModel('title_provider', 'title_model', p, m)}
                        placeholder="Choose a title model…"
                    />
                </div>
            </div>
        </div>
    );
}
