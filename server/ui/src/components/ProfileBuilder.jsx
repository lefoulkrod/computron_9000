import { useState, useEffect, useCallback, useMemo } from 'react';
import styles from './ProfileBuilder.module.css';
import ModelPicker from './ModelPicker.jsx';
import Button from './primitives/Button.jsx';
import Callout from './primitives/Callout.jsx';
import ConfirmButton from './primitives/ConfirmButton.jsx';
import { InferenceSettings, resolvePreset, detectPreset, INFERENCE_FIELDS, isSupported } from './inference';

const HELP_SECTIONS = [
    { title: 'Name', body: 'How this profile appears in the profile list and agent selector.' },
    { title: 'Description', body: 'A short summary of what this profile is tuned for. Shown below the name in the profile list.' },
    { title: 'Model', body: 'The model to use when this profile is active.' },
    { title: 'System Prompt', body: 'Instructions prepended to every conversation. Controls the agent\'s personality, constraints, and behavior. Supports markdown.' },
    { title: 'Skills', body: 'Toggle which tool groups the agent can access. Disabled skills are not available during inference.' },
    { title: 'Inference Preset', body: 'Quick presets that set temperature, sampling, and thinking for common workloads. Selecting a preset fills in the advanced values.' },
    { title: 'Temperature', body: '0.0 = deterministic, 0.7 = general use, 1.0+ = creative. Controls randomness in token selection.' },
    { title: 'Top K', body: 'Limits sampling to the K most probable tokens. 10 = factual, 40 = general, 100+ = creative.' },
    { title: 'Top P', body: 'Nucleus sampling — considers tokens whose cumulative probability exceeds P. 0.5 = focused, 0.9 = general, 1.0 = everything.' },
    { title: 'Repeat Penalty', body: '1.0 = off, 1.1 = general use, 1.5+ = strongly discourages repetition in long outputs.' },
    { title: 'Context Window', body: 'Maximum context window in tokens. Higher values allow longer conversations but use more memory (Ollama only).' },
    { title: 'Max Output (num_predict)', body: 'Maximum tokens the model can generate per turn. -1 = unlimited.' },
    { title: 'Iterations (max_iterations)', body: 'How many tool-call rounds the agent can chain per user message before stopping.' },
    { title: 'Thinking', body: 'When enabled, the model reasons step-by-step before answering. Good for math, logic, and code generation.' },
];

function _cloneProfile(profile) {
    return JSON.parse(JSON.stringify(profile));
}

export default function ProfileBuilder({
    profile,
    onSave,
    onDelete,
    onDuplicate,
    models,
    provider = 'ollama',
    availableSkills,
    deleteConflict,
    onDismissDeleteConflict,
}) {
    const [draft, setDraft] = useState(null);
    const [saveError, setSaveError] = useState(null);

    useEffect(() => {
        setSaveError(null);
        if (profile) {
            setDraft(_cloneProfile(profile));
        } else {
            setDraft(null);
        }
    }, [profile]);

    const activePreset = useMemo(() => {
        if (!draft) return null;
        return detectPreset(draft, provider);
    }, [draft, provider]);

    const update = useCallback((field, value) => {
        setDraft((prev) => (prev ? { ...prev, [field]: value } : prev));
    }, []);

    const applyPreset = useCallback((presetId) => {
        const values = resolvePreset(presetId, provider);
        if (!values) return;
        setDraft((prev) => {
            if (!prev) return prev;
            const next = { ...prev };
            for (const k of INFERENCE_FIELDS) {
                next[k] = null;
            }
            for (const [k, v] of Object.entries(values)) {
                if (isSupported(k, provider)) {
                    next[k] = v;
                }
            }
            return next;
        });
    }, [provider]);

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

    const handleSave = useCallback(async () => {
        if (!draft || !onSave) return;
        setSaveError(null);
        const result = await onSave(draft);
        if (result && result.ok === false && result.error) {
            setSaveError(result.error);
            if (result.error.error === 'default_agent_cannot_be_disabled') {
                setDraft((prev) => (prev ? { ...prev, enabled: true } : prev));
            }
        }
    }, [draft, onSave]);

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
                        <ConfirmButton
                            label="Delete"
                            confirmLabel="Confirm?"
                            busyLabel="Deleting…"
                            title="Delete this profile"
                            onConfirm={() => onDelete?.(profile.id)}
                        />
                        <div className={styles.actionsRight}>
                            <Button onClick={() => onDuplicate?.(profile.id)}>
                                Duplicate
                            </Button>
                            <Button onClick={handleRevert}>
                                Revert
                            </Button>
                            <Button variant="filled" onClick={handleSave}>
                                Save
                            </Button>
                        </div>
                    </div>

                {deleteConflict && (
                    <div className={styles.calloutSlot} data-testid="profile-delete-conflict">
                        <DeleteConflictCallout
                            conflict={deleteConflict}
                            onDismiss={onDismissDeleteConflict}
                        />
                    </div>
                )}

                <div className={styles.formBody}>
                    {/* 1. Identity */}
                    <section className={styles.section}>
                        <div className={styles.sectionLabel}>Identity</div>
                        <input
                            className={styles.nameInput}
                            type="text"
                            value={draft.name || ''}
                            onChange={(e) => update('name', e.target.value)}
                            placeholder="Profile name"
                        />
                        <input
                            className={styles.textInput}
                            type="text"
                            value={draft.description || ''}
                            onChange={(e) => update('description', e.target.value)}
                            placeholder="Short description"
                            disabled={false}
                        />
                        <label className={styles.enabledToggle} data-testid="profile-enabled-toggle">
                            <input
                                type="checkbox"
                                checked={draft.enabled !== false}
                                onChange={(e) => update('enabled', e.target.checked)}
                            />
                            <span className={styles.enabledToggleLabel}>
                                Enabled
                            </span>
                            <span className={styles.enabledHelp}>
                                Disabled profiles are hidden from the chat panel and can't be used
                                by spawn_agent. Scheduled tasks already using this profile still run.
                            </span>
                        </label>
                        {saveError && saveError.error === 'default_agent_cannot_be_disabled' && (
                            <div className={styles.errorPanel} data-testid="profile-save-error">
                                <span className={styles.errorTitle}>Can't disable the default agent</span>
                                <span>{saveError.message}</span>
                            </div>
                        )}
                    </section>

                    {/* 2. Model */}
                    <section className={styles.section} data-testid="profile-model-picker">
                        <div className={styles.sectionLabel}>Model</div>
                        <ModelPicker
                            models={models || []}
                            selected={draft.model || null}
                            onSelect={(name) => {
                                const meta = (models || []).find((m) => m.name === name);
                                setDraft((prev) => {
                                    if (!prev) return prev;
                                    const next = { ...prev, model: name || '' };
                                    if (meta?.context_window != null) {
                                        next.context_window = meta.context_window;
                                    }
                                    return next;
                                });
                            }}
                        />
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

                    {/* 5. Inference (presets + advanced) */}
                    <InferenceSettings
                        key={draft.id}
                        draft={draft}
                        provider={provider}
                        activePreset={activePreset}
                        onFieldChange={update}
                        onApplyPreset={applyPreset}
                    />
                </div>

            </div>

        </div>
    );
}

function DeleteConflictCallout({ conflict, onDismiss }) {
    const goals = useMemo(() => {
        const seen = new Set();
        const rows = [];
        for (const u of conflict.usage || []) {
            if (seen.has(u.goal_id)) continue;
            seen.add(u.goal_id);
            rows.push({ id: u.goal_id, description: u.goal_description });
        }
        return rows;
    }, [conflict.usage]);

    const description = goals.length === 1
        ? 'Remove this profile from the goal below, then try again.'
        : `Remove this profile from the ${goals.length} goals below, then try again.`;

    return (
        <Callout
            tone="danger"
            title="Can't delete — profile is in use"
            description={description}
            onDismiss={onDismiss}
        >
            <Callout.List>
                {goals.map(g => (
                    <Callout.Item key={g.id} kind="goal">{g.description}</Callout.Item>
                ))}
            </Callout.List>
        </Callout>
    );
}
