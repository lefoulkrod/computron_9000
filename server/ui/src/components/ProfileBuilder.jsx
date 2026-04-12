import { useState, useEffect, useCallback, useMemo } from 'react';
import styles from './ProfileBuilder.module.css';

const PRESETS = {
    balanced: { temperature: 0.7 },
    creative: { temperature: 1.0, top_p: 0.95 },
    precise:  { temperature: 0.2, top_k: 40 },
    code:     { temperature: 0.3, think: true },
};

const PRESET_META = [
    { id: 'balanced', label: 'Balanced', hint: '0.7 temp' },
    { id: 'creative', label: 'Creative', hint: '1.0 temp, 0.95 top_p' },
    { id: 'precise',  label: 'Precise',  hint: '0.2 temp, 40 top_k' },
    { id: 'code',     label: 'Code',     hint: '0.3 temp, think' },
];

const INFERENCE_FIELDS = ['temperature', 'top_k', 'top_p', 'repeat_penalty', 'think'];

const HELP_SECTIONS = [
    { title: 'Icon & Name', body: 'Click the icon to pick a different emoji. The name is how this profile appears in the profile list and agent selector.' },
    { title: 'Description', body: 'A short summary of what this profile is tuned for. Shown below the name in the profile list.' },
    { title: 'Model', body: 'The Ollama model to use when this profile is active. Leave blank to use the system default.' },
    { title: 'System Prompt', body: 'Instructions prepended to every conversation. Controls the agent\'s personality, constraints, and behavior. Supports markdown.' },
    { title: 'Skills', body: 'Toggle which tool groups the agent can access. Disabled skills are not available during inference.' },
    { title: 'Inference Preset', body: 'Quick presets that set temperature, sampling, and thinking for common workloads. Selecting a preset fills in the advanced values.' },
    { title: 'Temperature', body: '0.0 = deterministic, 0.7 = general use, 1.0+ = creative. Controls randomness in token selection.' },
    { title: 'Top K', body: 'Limits sampling to the K most probable tokens. 10 = factual, 40 = general, 100+ = creative.' },
    { title: 'Top P', body: 'Nucleus sampling — considers tokens whose cumulative probability exceeds P. 0.5 = focused, 0.9 = general, 1.0 = everything.' },
    { title: 'Repeat Penalty', body: '1.0 = off, 1.1 = general use, 1.5+ = strongly discourages repetition in long outputs.' },
    { title: 'Context (num_ctx)', body: 'Maximum context window in K tokens. Higher values allow longer conversations but use more memory.' },
    { title: 'Max Output (num_predict)', body: 'Maximum tokens the model can generate per turn. -1 = unlimited.' },
    { title: 'Iterations (max_iterations)', body: 'How many tool-call rounds the agent can chain per user message before stopping.' },
    { title: 'Thinking', body: 'When enabled, the model reasons step-by-step before answering. Good for math, logic, and code generation.' },
];

function _detectPreset(draft) {
    for (const [id, fields] of Object.entries(PRESETS)) {
        const presetKeys = Object.keys(fields);
        const allMatch = presetKeys.every((k) => {
            const draftVal = draft[k];
            const presetVal = fields[k];
            if (typeof presetVal === 'boolean') return draftVal === presetVal;
            return Number(draftVal) === presetVal;
        });
        if (!allMatch) continue;

        const otherKeys = INFERENCE_FIELDS.filter((k) => !presetKeys.includes(k));
        const othersNull = otherKeys.every((k) => draft[k] == null || draft[k] === '');
        if (othersNull) return id;
    }
    return null;
}

function _cloneProfile(profile) {
    return JSON.parse(JSON.stringify(profile));
}

function ChevronIcon({ open }) {
    return (
        <svg
            className={`${styles.chevron} ${open ? styles.chevronOpen : ''}`}
            viewBox="0 0 16 16"
            fill="currentColor"
        >
            <path d="M6.22 4.22a.75.75 0 0 1 1.06 0l3.25 3.25a.75.75 0 0 1 0 1.06l-3.25 3.25a.75.75 0 0 1-1.06-1.06L8.94 8 6.22 5.28a.75.75 0 0 1 0-1.06Z" />
        </svg>
    );
}

const ADVANCED_HELP = {
    temperature: '0.0 = deterministic, 0.7 = general, 1.0+ = creative',
    top_k: '10 = factual, 40 = general, 100+ = creative',
    top_p: '0.5 = focused, 0.9 = general, 1.0 = everything',
    repeat_penalty: '1.0 = off, 1.1 = general, 1.5+ = strongly discourages repetition',
    context: 'Context window in tokens. Higher = more memory, slower',
    max_output: 'Max tokens per response. Leave empty for unlimited',
    iterations: 'Tool-call rounds per turn. Leave empty for unlimited',
    thinking: 'Step-by-step reasoning before answering. Good for math, logic, code',
};

export default function ProfileBuilder({ profile, onSave, onDelete, onDuplicate, models, availableSkills }) {
    const [draft, setDraft] = useState(null);
    const [showAdvanced, setShowAdvanced] = useState(false);
    const [showIconPicker, setShowIconPicker] = useState(false);

    // Clone profile into local draft whenever the prop changes
    useEffect(() => {
        setShowIconPicker(false);
        setShowAdvanced(false);
        if (profile) {
            setDraft(_cloneProfile(profile));
        } else {
            setDraft(null);
        }
    }, [profile]);

    const activePreset = useMemo(() => {
        if (!draft) return null;
        return _detectPreset(draft);
    }, [draft]);

    const update = useCallback((field, value) => {
        setDraft((prev) => (prev ? { ...prev, [field]: value } : prev));
    }, []);

    const updateInference = useCallback((field, value) => {
        setDraft((prev) => (prev ? { ...prev, [field]: value } : prev));
    }, []);

    const applyPreset = useCallback((presetId) => {
        const values = PRESETS[presetId];
        if (!values) return;
        setDraft((prev) => {
            if (!prev) return prev;
            const next = { ...prev };
            // Clear all inference fields first
            for (const k of INFERENCE_FIELDS) {
                next[k] = null;
            }
            // Apply preset values
            for (const [k, v] of Object.entries(values)) {
                next[k] = v;
            }
            return next;
        });
    }, []);

    const toggleSkill = useCallback((skill) => {
        setDraft((prev) => {
            if (!prev) return prev;
            const current = prev.skills || [];
            const has = current.includes(skill);
            return {
                ...prev,
                skills: has ? current.filter((s) => s !== skill) : [...current, skill],
            };
        });
    }, []);

    const handleRevert = useCallback(() => {
        if (profile) {
            setDraft(_cloneProfile(profile));
        }
    }, [profile]);

    const handleSave = useCallback(() => {
        if (draft && onSave) {
            onSave(draft);
        }
    }, [draft, onSave]);

    // Empty state
    if (!profile) {
        return (
            <div className={styles.wrapper}>
                <div className={styles.emptyState}>
                    Select a profile to edit
                </div>
            </div>
        );
    }

    if (!draft) return null;


    return (
        <div className={styles.wrapper}>
            <div className={styles.editor}>
                {/* Actions bar */}
                <div className={styles.actionsBar}>
                        <button
                            className={styles.deleteBtn}
                            onClick={() => onDelete?.(profile.id)}
                        >
                            Delete
                        </button>
                        <div className={styles.actionsRight}>
                            <button
                                className={styles.secondaryBtn}
                                onClick={() => onDuplicate?.(profile.id)}
                            >
                                Duplicate
                            </button>
                            <button
                                className={styles.secondaryBtn}
                                onClick={handleRevert}
                            >
                                Revert
                            </button>
                            <button
                                className={styles.primaryBtn}
                                onClick={handleSave}
                            >
                                Save
                            </button>
                        </div>
                    </div>

                <div className={styles.formBody}>
                    {/* 1. Identity */}
                    <section className={styles.section}>
                        <div className={styles.sectionLabel}>Identity</div>
                        <div className={styles.identityRow}>
                            <div style={{ position: 'relative' }}>
                                <button
                                    className={styles.iconPicker}
                                    onClick={() => setShowIconPicker(v => !v)}
                                    title="Change icon"
                                >
                                    {draft.icon || '\u{1F916}'}
                                </button>
                                {showIconPicker && (
                                    <div className={styles.emojiGrid}>
                                        {['🤖','💻','🔍','✍️','📊','🧪','🔧','🎯','🌐','📝','🧠','🚀','📡','🎨','🛡️','⚡','🔬','📈','🗂️','💡'].map(e => (
                                            <button
                                                key={e}
                                                className={styles.emojiOption}
                                                onClick={() => { update('icon', e); setShowIconPicker(false); }}
                                            >{e}</button>
                                        ))}
                                    </div>
                                )}
                            </div>
                            <input
                                className={styles.nameInput}
                                type="text"
                                value={draft.name || ''}
                                onChange={(e) => update('name', e.target.value)}
                                placeholder="Profile name"
                            />
                        </div>
                        <input
                            className={styles.textInput}
                            type="text"
                            value={draft.description || ''}
                            onChange={(e) => update('description', e.target.value)}
                            placeholder="Short description"
                            disabled={false}
                        />
                    </section>

                    {/* 2. Model */}
                    <section className={styles.section}>
                        <div className={styles.sectionLabel}>Model</div>
                        <select
                            className={styles.selectInput}
                            value={draft.model || ''}
                            onChange={(e) => update('model', e.target.value)}
                        >
                            <option value="">Inherit from default agent</option>
                            {(models || []).map((m) => (
                                <option key={m.name} value={m.name}>{m.name}</option>
                            ))}
                        </select>
                    </section>

                    {/* 3. System Prompt */}
                    <section className={styles.section}>
                        <div className={styles.sectionLabel}>System Prompt</div>
                        <textarea
                            className={styles.promptTextarea}
                            value={draft.system_prompt || ''}
                            onChange={(e) => update('system_prompt', e.target.value)}
                            placeholder="System prompt..."
                            rows={8}
                            disabled={false}
                        />
                    </section>

                    {/* 4. Skills */}
                    <section className={styles.section}>
                        <div className={styles.sectionLabel}>Skills</div>
                        <div className={styles.chipGrid}>
                            {(availableSkills || []).map((skill) => {
                                const active = (draft.skills || []).includes(skill);
                                return (
                                    <button
                                        key={skill}
                                        className={`${styles.chip} ${active ? styles.chipActive : ''}`}
                                        onClick={() => toggleSkill(skill)}
                                            >
                                        {active && <span className={styles.chipCheck}>&#x2713;</span>}
                                        {skill}
                                    </button>
                                );
                            })}
                        </div>
                    </section>

                    {/* 5. Inference Preset */}
                    <section className={styles.section}>
                        <div className={styles.sectionLabel}>Inference Preset</div>
                        <div className={styles.presetGrid}>
                            {PRESET_META.map((p) => (
                                <button
                                    key={p.id}
                                    className={`${styles.presetBtn} ${activePreset === p.id ? styles.presetActive : ''}`}
                                    onClick={() => applyPreset(p.id)}
                                    >
                                    <span className={styles.presetLabel}>{p.label}</span>
                                    <span className={styles.presetHint}>{p.hint}</span>
                                </button>
                            ))}
                        </div>
                    </section>

                    {/* 6. Advanced Settings */}
                    <section className={styles.section}>
                        <button
                            className={styles.advancedToggle}
                            onClick={() => setShowAdvanced((v) => !v)}
                        >
                            <ChevronIcon open={showAdvanced} />
                            Advanced Settings
                        </button>

                        {showAdvanced && (
                            <div className={styles.advancedBody}>
                                <div className={styles.advancedField}>
                                    <label className={styles.fieldRow}>
                                        <span className={styles.fieldLabel}>Temperature</span>
                                        <input className={styles.numInput} type="number" value={draft.temperature ?? ''} onChange={(e) => updateInference('temperature', e.target.value === '' ? null : Number(e.target.value))} min={0} max={2} step={0.1} placeholder="auto" />
                                    </label>
                                    <span className={styles.fieldHint}>{ADVANCED_HELP.temperature}</span>
                                </div>
                                <div className={styles.advancedField}>
                                    <label className={styles.fieldRow}>
                                        <span className={styles.fieldLabel}>Top K</span>
                                        <input className={styles.numInput} type="number" value={draft.top_k ?? ''} onChange={(e) => updateInference('top_k', e.target.value === '' ? null : Number(e.target.value))} min={0} step={1} placeholder="auto" />
                                    </label>
                                    <span className={styles.fieldHint}>{ADVANCED_HELP.top_k}</span>
                                </div>
                                <div className={styles.advancedField}>
                                    <label className={styles.fieldRow}>
                                        <span className={styles.fieldLabel}>Top P</span>
                                        <input className={styles.numInput} type="number" value={draft.top_p ?? ''} onChange={(e) => updateInference('top_p', e.target.value === '' ? null : Number(e.target.value))} min={0} max={1} step={0.05} placeholder="auto" />
                                    </label>
                                    <span className={styles.fieldHint}>{ADVANCED_HELP.top_p}</span>
                                </div>
                                <div className={styles.advancedField}>
                                    <label className={styles.fieldRow}>
                                        <span className={styles.fieldLabel}>Repeat Penalty</span>
                                        <input className={styles.numInput} type="number" value={draft.repeat_penalty ?? ''} onChange={(e) => updateInference('repeat_penalty', e.target.value === '' ? null : Number(e.target.value))} min={0} step={0.05} placeholder="auto" />
                                    </label>
                                    <span className={styles.fieldHint}>{ADVANCED_HELP.repeat_penalty}</span>
                                </div>
                                <div className={styles.advancedField}>
                                    <label className={styles.fieldRow}>
                                        <span className={styles.fieldLabel}>Context</span>
                                        <input className={styles.numInput} type="number" value={draft.num_ctx ?? ''} onChange={(e) => update('num_ctx', e.target.value === '' ? null : Number(e.target.value))} min={1} placeholder="auto" />
                                    </label>
                                    <span className={styles.fieldHint}>{ADVANCED_HELP.context}</span>
                                </div>
                                <div className={styles.advancedField}>
                                    <label className={styles.fieldRow}>
                                        <span className={styles.fieldLabel}>Max Output</span>
                                        <input className={styles.numInput} type="number" value={draft.num_predict ?? ''} onChange={(e) => update('num_predict', e.target.value === '' ? null : Number(e.target.value))} min={-1} step={1} placeholder="unlimited" />
                                    </label>
                                    <span className={styles.fieldHint}>{ADVANCED_HELP.max_output}</span>
                                </div>
                                <div className={styles.advancedField}>
                                    <label className={styles.fieldRow}>
                                        <span className={styles.fieldLabel}>Iterations</span>
                                        <input className={styles.numInput} type="number" value={draft.max_iterations ?? ''} onChange={(e) => update('max_iterations', e.target.value === '' ? null : Number(e.target.value))} min={1} step={1} placeholder="unlimited" />
                                    </label>
                                    <span className={styles.fieldHint}>{ADVANCED_HELP.iterations}</span>
                                </div>
                                <div className={styles.advancedField}>
                                    <div className={styles.fieldRow}>
                                        <span className={styles.fieldLabel}>Thinking</span>
                                        <label className={styles.toggleLabel}>
                                            <input type="checkbox" className={styles.toggleInput} checked={draft.think || false} onChange={(e) => updateInference('think', e.target.checked || null)} />
                                            <span className={styles.toggle} />
                                        </label>
                                    </div>
                                    <span className={styles.fieldHint}>{ADVANCED_HELP.thinking}</span>
                                </div>
                            </div>
                        )}
                    </section>
                </div>

            </div>

        </div>
    );
}
