import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import ModelPicker from './ModelPicker.jsx';
import styles from './SetupWizard.module.css';

const STEPS = ['Welcome', 'Provider', 'Main Model', 'Vision Model', 'Ready'];

// Internal provider keys
const PROVIDER_OLLAMA = 'ollama';
const PROVIDER_OPENAI_COMPAT = 'openai-compat';
const PROVIDER_CLOUD = 'cloud';

const PROVIDER_LABELS = {
    openai: 'OpenAI API',
    anthropic: 'Anthropic API',
    openrouter: 'OpenRouter',
    openai_compat: 'OpenAI-compatible',
};

// Defaults pre-filled in the connect step; the server still requires the
// URL be present in the request body.
const OLLAMA_DEFAULT_URL = 'http://host.docker.internal:11434';
const OPENAI_COMPAT_DEFAULT_URL = 'http://localhost:1234/v1';

function ProgressBar({ currentStep }) {
    return (
        <div className={styles.progressBar} role="list" aria-label="Setup progress">
            {STEPS.map((label, i) => {
                const done = i < currentStep;
                const active = i === currentStep;
                return (
                    <div
                        key={label}
                        className={styles.progressStep}
                        role="listitem"
                        aria-label={`${label}${done ? ', completed' : active ? ', current step' : ''}`}
                    >
                        {i > 0 && (
                            <div
                                className={`${styles.progressLine} ${done ? styles.progressLineDone : ''}`}
                                aria-hidden="true"
                            />
                        )}
                        <div
                            className={`${styles.progressCircle} ${active ? styles.progressCircleActive : ''} ${done ? styles.progressCircleDone : ''}`}
                            aria-hidden="true"
                        >
                            {i + 1}
                        </div>
                    </div>
                );
            })}
        </div>
    );
}

function ModelCard({ name, value, description, model, selected, onSelect }) {
    return (
        <button
            className={`${styles.modelCard} ${selected ? styles.modelCardSelected : ''}`}
            onClick={() => onSelect(value ?? name)}
            type="button"
            aria-pressed={selected}
        >
            <span className={`${styles.radio} ${selected ? styles.radioSelected : ''}`} aria-hidden="true" />
            <div className={styles.modelInfo}>
                <span className={styles.modelName}>{name}</span>
                {description && <span className={styles.modelDesc}>{description}</span>}
                {model && (
                    <div className={styles.badges}>
                        {model.parameter_size && (
                            <span className={`${styles.badge} ${styles.badgeParams}`}>
                                {model.parameter_size}
                            </span>
                        )}
                        {model.quantization_level && (
                            <span className={`${styles.badge} ${styles.badgeQuant}`}>
                                {model.quantization_level}
                            </span>
                        )}
                        {model.family && (
                            <span className={`${styles.badge} ${styles.badgeFamily}`}>
                                {model.family}
                            </span>
                        )}
                        {model.is_cloud && (
                            <span className={`${styles.badge} ${styles.badgeCloud}`}>cloud</span>
                        )}
                        {(model.capabilities || []).includes('vision') && (
                            <span className={`${styles.badge} ${styles.badgeVision}`}>vision</span>
                        )}
                    </div>
                )}
            </div>
        </button>
    );
}

export default function SetupWizard({ onComplete }) {
    const [step, setStep] = useState(0);

    // Provider step state
    const [selectedProvider, setSelectedProvider] = useState(null);
    const [cloudProvider, setCloudProvider] = useState('anthropic');
    const [providerUrl, setProviderUrl] = useState('');
    const [providerApiKey, setProviderApiKey] = useState('');
    const [providerError, setProviderError] = useState(null);
    const [providerSaving, setProviderSaving] = useState(false);

    // Model step state. The ModelPicker handles its own list fetching;
    // we just track which model is picked and its metadata (for context_window).
    const [selectedMain, setSelectedMain] = useState(null);
    const [mainModelMeta, setMainModelMeta] = useState(null);
    // undefined = not chosen yet; null = explicit skip; string = model name
    const [selectedVision, setSelectedVision] = useState(undefined);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState(null);

    // The provider name as stored in settings / on profiles ('ollama',
    // 'openai_compat', 'anthropic', 'openai', ...).
    const resolvedProviderName = useMemo(() => (
        selectedProvider === PROVIDER_CLOUD
            ? cloudProvider
            : selectedProvider === PROVIDER_OPENAI_COMPAT
                ? 'openai_compat'
                : 'ollama'
    ), [selectedProvider, cloudProvider]);

    // Refs for a11y
    const cardRef = useRef(null);
    const stepTitleRef = useRef(null);

    // Focus first element in dialog on mount
    useEffect(() => {
        const first = cardRef.current?.querySelector(
            'button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        first?.focus();
    }, []);

    // Move focus to step title when step changes
    useEffect(() => {
        stepTitleRef.current?.focus();
    }, [step]);

    // Focus trap: keep Tab/Shift+Tab inside the dialog
    useEffect(() => {
        const handleKeyDown = (e) => {
            if (e.key !== 'Tab' || !cardRef.current) return;
            const focusable = Array.from(cardRef.current.querySelectorAll(
                'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
            ));
            if (focusable.length === 0) return;
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (e.shiftKey) {
                if (document.activeElement === first) { e.preventDefault(); last.focus(); }
            } else {
                if (document.activeElement === last) { e.preventDefault(); first.focus(); }
            }
        };
        document.addEventListener('keydown', handleKeyDown);
        return () => document.removeEventListener('keydown', handleKeyDown);
    }, []);



    // ── Provider step: create+probe via POST /api/providers ─────────
    // One server-side call. The server picks the storage (direct settings
    // entry vs. brokered vault integration) from the body shape, then
    // probes the new provider — 201 on success, 503 with a message if it
    // can't connect.
    const handleSaveProvider = useCallback(async () => {
        setProviderSaving(true);
        setProviderError(null);

        const body = { name: resolvedProviderName };
        if (selectedProvider === PROVIDER_OLLAMA) {
            body.base_url = providerUrl.trim() || OLLAMA_DEFAULT_URL;
        } else if (selectedProvider === PROVIDER_OPENAI_COMPAT) {
            body.base_url = providerUrl.trim() || OPENAI_COMPAT_DEFAULT_URL;
            if (providerApiKey.trim()) body.api_key = providerApiKey.trim();
        } else {
            body.api_key = providerApiKey.trim();
        }

        try {
            const res = await fetch('/api/providers', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                setProviderError(data.message || data.error || `Failed to connect (${res.status})`);
                return;
            }
            setStep((s) => s + 1);
        } catch (err) {
            setProviderError(err.message);
        } finally {
            setProviderSaving(false);
        }
    }, [selectedProvider, resolvedProviderName, providerUrl, providerApiKey]);

    // ── Final save: server-side orchestration ───────────────────────
    const handleFinish = useCallback(async () => {
        setSaving(true);
        setError(null);
        try {
            const res = await fetch('/api/setup/complete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    provider: resolvedProviderName,
                    main_model: selectedMain,
                    vision_model: selectedVision,
                    context_window: mainModelMeta?.context_window ?? null,
                }),
            });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                setError(data.error || `Setup failed (${res.status})`);
                setSaving(false);
                return;
            }
            onComplete();
        } catch (err) {
            setError(`Connection error: ${err.message}`);
            setSaving(false);
        }
    }, [selectedMain, selectedVision, mainModelMeta, resolvedProviderName, onComplete]);

    const canContinue =
        step === 0 ||
        (step === 1 && selectedProvider !== null && !providerSaving) ||
        (step === 2 && selectedMain !== null) ||
        (step === 3 && selectedVision !== undefined) ||
        step === 4;

    const handleNext = () => {
        if (step === 1) { handleSaveProvider(); return; }
        if (step === 4) { handleFinish(); return; }
        setStep((s) => s + 1);
    };

    const handleBack = () => {
        if (step === 2) {
            setSelectedMain(null);
            setMainModelMeta(null);
        }
        if (step === 3) {
            setSelectedVision(undefined);
        }
        setStep((s) => s - 1);
    };

    const buttonLabel =
        step === 0 ? 'Get Started'
            : step === 1 ? (providerSaving ? 'Connecting…' : 'Connect')
                : step === 4 ? 'Start Chatting'
                    : 'Continue';

    const stepTitleId = 'wizard-step-title';

    return (
        <div className={styles.overlay}>
            <div
                ref={cardRef}
                className={styles.card}
                role="dialog"
                aria-modal="true"
                aria-labelledby={stepTitleId}
            >
                <ProgressBar currentStep={step} />

                {/* ── Step 0: Welcome ──────────────────────────────────── */}
                {step === 0 && (
                    <div className={styles.stepContent}>
                        <h1
                            id={stepTitleId}
                            ref={stepTitleRef}
                            className={styles.title}
                            tabIndex={-1}
                        >
                            Welcome to Computron
                        </h1>
                        <p className={styles.subtitle}>
                            Let's get you set up. We'll connect to your LLM provider, then
                            pick a main model and an optional vision model.
                        </p>
                    </div>
                )}

                {/* ── Step 1: Provider ─────────────────────────────────── */}
                {step === 1 && (
                    <div className={styles.stepContent}>
                        <h1
                            id={stepTitleId}
                            ref={stepTitleRef}
                            className={styles.title}
                            tabIndex={-1}
                        >
                            Choose your LLM provider
                        </h1>
                        <p className={styles.subtitle}>
                            Connect to a local model server or a cloud API.
                        </p>

                        <div className={styles.modelList}>
                            {[
                                {
                                    key: PROVIDER_OLLAMA,
                                    name: 'Ollama (local)',
                                    desc: 'Run models on your own machine or in the cloud',
                                },
                                {
                                    key: PROVIDER_OPENAI_COMPAT,
                                    name: 'OpenAI-compatible endpoint',
                                    desc: 'LM Studio, vLLM, Groq, Together AI, and others',
                                },
                                {
                                    key: PROVIDER_CLOUD,
                                    name: 'Cloud API',
                                    desc: 'Anthropic, OpenAI, or OpenRouter',
                                },
                            ].map(({ key, name, desc }) => (
                                <ModelCard
                                    key={key}
                                    name={name}
                                    value={key}
                                    description={desc}
                                    selected={selectedProvider === key}
                                    onSelect={(k) => { setSelectedProvider(k); setProviderError(null); }}
                                />
                            ))}
                        </div>

                        {/* Conditional fields */}
                        {selectedProvider === PROVIDER_OLLAMA && (
                            <div className={styles.providerFields}>
                                <div className={styles.field}>
                                    <label htmlFor="ollama-url" className={styles.fieldLabel}>
                                        Ollama URL
                                    </label>
                                    <input
                                        id="ollama-url"
                                        type="url"
                                        className={styles.fieldInput}
                                        value={providerUrl}
                                        onChange={(e) => setProviderUrl(e.target.value)}
                                        placeholder="http://host.docker.internal:11434"
                                        aria-describedby="ollama-url-hint"
                                    />
                                    <div id="ollama-url-hint" className={styles.fieldHint}>
                                        macOS/Windows: use <code>host.docker.internal</code>.
                                        Linux: start with <code>--network=host</code> and use <code>localhost</code>.
                                    </div>
                                </div>
                            </div>
                        )}

                        {selectedProvider === PROVIDER_OPENAI_COMPAT && (
                            <div className={styles.providerFields}>
                                <div className={styles.field}>
                                    <label htmlFor="compat-url" className={styles.fieldLabel}>
                                        Server URL
                                    </label>
                                    <input
                                        id="compat-url"
                                        type="url"
                                        className={styles.fieldInput}
                                        value={providerUrl}
                                        onChange={(e) => setProviderUrl(e.target.value)}
                                        placeholder="http://localhost:1234/v1"
                                        aria-describedby="compat-url-hint"
                                    />
                                    <div id="compat-url-hint" className={styles.fieldHint}>
                                        Base URL of your OpenAI-compatible server.
                                    </div>
                                </div>
                                <div className={styles.field}>
                                    <label htmlFor="compat-key" className={styles.fieldLabel}>
                                        API Key <span className={styles.fieldHint}>(optional)</span>
                                    </label>
                                    <input
                                        id="compat-key"
                                        type="password"
                                        className={styles.fieldInput}
                                        value={providerApiKey}
                                        onChange={(e) => setProviderApiKey(e.target.value)}
                                        placeholder="Leave blank if not required"
                                        autoComplete="new-password"
                                    />
                                </div>
                            </div>
                        )}

                        {selectedProvider === PROVIDER_CLOUD && (
                            <div className={styles.providerFields}>
                                <div className={styles.field}>
                                    <label htmlFor="cloud-provider" className={styles.fieldLabel}>
                                        Provider
                                    </label>
                                    <select
                                        id="cloud-provider"
                                        className={styles.cloudSelect}
                                        value={cloudProvider}
                                        onChange={(e) => setCloudProvider(e.target.value)}
                                    >
                                        <option value="anthropic">Anthropic</option>
                                        <option value="openai">OpenAI</option>
                                        <option value="openrouter">OpenRouter</option>
                                    </select>
                                </div>
                                <div className={styles.field}>
                                    <label htmlFor="cloud-key" className={styles.fieldLabel}>
                                        API Key
                                    </label>
                                    <input
                                        id="cloud-key"
                                        type="password"
                                        className={styles.fieldInput}
                                        value={providerApiKey}
                                        onChange={(e) => setProviderApiKey(e.target.value)}
                                        placeholder="sk-..."
                                        autoComplete="new-password"
                                        aria-describedby="cloud-key-hint"
                                    />
                                    <div id="cloud-key-hint" className={styles.fieldHint}>
                                        Your API key is stored locally and never sent to us.
                                    </div>
                                </div>
                            </div>
                        )}

                        {providerError && (
                            <div className={styles.providerError} role="alert">
                                {providerError}
                            </div>
                        )}
                    </div>
                )}

                {/* ── Step 2: Main Model ───────────────────────────────── */}
                {step === 2 && (
                    <div className={styles.stepContent}>
                        <h1
                            id={stepTitleId}
                            ref={stepTitleRef}
                            className={styles.title}
                            tabIndex={-1}
                        >
                            Choose your main model
                        </h1>
                        <p className={styles.subtitle}>
                            This will be set as the default model for all built-in agent
                            profiles. You can change individual profiles later in Settings.
                        </p>
                        <ModelPicker
                            providers={[{ name: resolvedProviderName, label: PROVIDER_LABELS[resolvedProviderName] || resolvedProviderName }]}
                            selectedProvider={resolvedProviderName}
                            selectedModel={selectedMain}
                            onSelect={(_p, m, meta) => {
                                setSelectedMain(m);
                                setMainModelMeta(meta);
                            }}
                            placeholder="Choose a main model…"
                            defaultOpen
                            inline
                        />
                    </div>
                )}

                {/* ── Step 3: Vision Model ─────────────────────────────── */}
                {step === 3 && (
                    <div className={styles.stepContent}>
                        <h1
                            id={stepTitleId}
                            ref={stepTitleRef}
                            className={styles.title}
                            tabIndex={-1}
                        >
                            Choose a vision model
                        </h1>
                        <p className={styles.subtitle}>
                            Used for understanding images and screenshots. Choose a model
                            that supports vision (image input).
                        </p>

                        <ModelPicker
                            providers={[{ name: resolvedProviderName, label: PROVIDER_LABELS[resolvedProviderName] || resolvedProviderName }]}
                            selectedProvider={resolvedProviderName}
                            selectedModel={selectedVision || null}
                            onSelect={(_p, m) => setSelectedVision(m)}
                            placeholder="Choose a vision model…"
                            capability="vision"
                            defaultOpen
                            inline
                        />

                        <button
                            type="button"
                            className={styles.skipBtn}
                            onClick={() => setSelectedVision(null)}
                        >
                            Skip — I'll configure this later
                        </button>
                    </div>
                )}

                {/* ── Step 4: Ready ────────────────────────────────────── */}
                {step === 4 && (
                    <div className={styles.stepContent}>
                        <div className={styles.stepIcon} aria-hidden="true">&#10003;</div>
                        <h1
                            id={stepTitleId}
                            ref={stepTitleRef}
                            className={styles.title}
                            tabIndex={-1}
                        >
                            You're all set
                        </h1>
                        <div className={styles.summary}>
                            <div className={styles.summaryRow}>
                                <span className={styles.summaryLabel}>Provider</span>
                                <span className={styles.summaryValue}>
                                    {selectedProvider === PROVIDER_OLLAMA ? 'Ollama'
                                        : selectedProvider === PROVIDER_OPENAI_COMPAT ? 'OpenAI-compatible'
                                            : cloudProvider === 'anthropic' ? 'Anthropic' : 'OpenAI'}
                                </span>
                            </div>
                            <div className={styles.summaryRow}>
                                <span className={styles.summaryLabel}>Main model</span>
                                <span className={styles.summaryValue}>{selectedMain}</span>
                            </div>
                            <div className={styles.summaryRow}>
                                <span className={styles.summaryLabel}>Vision model</span>
                                <span className={styles.summaryValue}>
                                    {selectedVision || 'None'}
                                </span>
                            </div>
                        </div>
                    </div>
                )}

                {error && (
                    <div className={styles.error} role="alert">{error}</div>
                )}

                <div className={styles.nav}>
                    {step > 0 && step < 4 && (
                        <button
                            className={styles.backBtn}
                            onClick={handleBack}
                            type="button"
                        >
                            Back
                        </button>
                    )}
                    <button
                        className={styles.nextBtn}
                        onClick={handleNext}
                        disabled={!canContinue || saving}
                        type="button"
                    >
                        {saving ? 'Saving...' : buttonLabel}
                    </button>
                </div>
            </div>
        </div>
    );
}
