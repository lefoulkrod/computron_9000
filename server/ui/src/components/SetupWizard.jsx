import { useState, useEffect, useCallback, useRef } from 'react';
import styles from './SetupWizard.module.css';

const STEPS = ['Welcome', 'Provider', 'Main Model', 'Vision Model', 'Ready'];

// Internal provider keys
const PROVIDER_OLLAMA = 'ollama';
const PROVIDER_OPENAI_COMPAT = 'openai-compat';
const PROVIDER_CLOUD = 'cloud';

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

function ModelCard({ model, selected, onSelect }) {
    return (
        <button
            className={`${styles.modelCard} ${selected ? styles.modelCardSelected : ''}`}
            onClick={() => onSelect(model.name)}
            type="button"
            aria-pressed={selected}
        >
            <span className={`${styles.radio} ${selected ? styles.radioSelected : ''}`} aria-hidden="true" />
            <div className={styles.modelInfo}>
                <span className={styles.modelName}>{model.name}</span>
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
            </div>
        </button>
    );
}

// Receives a key prop from the parent that changes on each new error, so the
// component remounts and moves focus to the panel automatically.
function ModelsErrorPanel({ error, onRetry, loading, selectedProvider }) {
    const ref = useRef(null);
    useEffect(() => { ref.current?.focus(); }, []);

    const isOllama = !selectedProvider || selectedProvider === PROVIDER_OLLAMA;
    const isCloud = selectedProvider === PROVIDER_CLOUD;

    return (
        <div ref={ref} className={styles.errorPanel} role="alert" tabIndex={-1}>
            <div className={styles.errorTitle}>
                {isOllama ? "Can't reach Ollama" : "Can't reach provider"}
            </div>
            <div className={styles.errorMessage}>{error.message}</div>
            {error.llmHost && (
                <div className={styles.errorDetail}>
                    Trying: <code>{error.llmHost}</code>
                </div>
            )}
            {isOllama && (
                <ul className={styles.errorHints}>
                    <li>Make sure Ollama is running on the host (<code>ollama serve</code>).</li>
                    <li>
                        On macOS / Windows / WSL2, use{' '}
                        <code>http://host.docker.internal:11434</code> as the URL.
                    </li>
                    <li>
                        On Linux, start the container with <code>--network=host</code> and
                        use <code>http://localhost:11434</code>.
                    </li>
                </ul>
            )}
            {selectedProvider === PROVIDER_OPENAI_COMPAT && (
                <ul className={styles.errorHints}>
                    <li>Check that your server is running and the URL is correct.</li>
                    <li>Make sure the server is reachable from this container.</li>
                </ul>
            )}
            {isCloud && (
                <ul className={styles.errorHints}>
                    <li>Check that your API key is correct.</li>
                    <li>Ensure you have a working internet connection.</li>
                </ul>
            )}
            <button
                className={styles.retryBtn}
                type="button"
                onClick={onRetry}
                disabled={loading}
            >
                {loading ? 'Retrying…' : 'Retry'}
            </button>
        </div>
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

    // Model step state
    const [allModels, setAllModels] = useState([]);
    const [visionModels, setVisionModels] = useState([]);
    const [selectedMain, setSelectedMain] = useState(null);
    // undefined = not chosen yet; null = explicit skip; string = model name
    const [selectedVision, setSelectedVision] = useState(undefined);
    const [saving, setSaving] = useState(false);
    const [modelsError, setModelsError] = useState(null);
    const [modelsLoading, setModelsLoading] = useState(false);
    const [error, setError] = useState(null);

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

    // Auto-skip vision when cloud provider is selected (cloud models include vision)
    useEffect(() => {
        if (step === 3 && selectedProvider === PROVIDER_CLOUD && selectedVision === undefined) {
            setSelectedVision(null);
        }
    }, [step, selectedProvider, selectedVision]);

    const fetchModels = useCallback(async (url, setter) => {
        setModelsLoading(true);
        setModelsError(null);
        try {
            const res = await fetch(url);
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                setModelsError({
                    message: data.message || `Request failed (${res.status})`,
                    llmHost: data.llm_host || null,
                });
                return;
            }
            setter(data.models || []);
        } catch (err) {
            setModelsError({ message: err.message, llmHost: null });
        } finally {
            setModelsLoading(false);
        }
    }, []);

    // Fetch all models when entering step 2 (if not already populated by the probe)
    useEffect(() => {
        if (step !== 2 || allModels.length > 0) return;
        fetchModels('/api/models', setAllModels);
    }, [step, allModels.length, fetchModels]);

    // Fetch vision models when entering step 3
    useEffect(() => {
        if (step !== 3 || visionModels.length > 0) return;
        fetchModels('/api/models?capability=vision', setVisionModels);
    }, [step, visionModels.length, fetchModels]);

    const retryFetch = () => {
        if (step === 2) fetchModels('/api/models', setAllModels);
        else if (step === 3) fetchModels('/api/models?capability=vision', setVisionModels);
    };

    // ── Provider step: save settings and probe connection ───────────
    const handleSaveProvider = useCallback(async () => {
        setProviderSaving(true);
        setProviderError(null);

        const providerName = selectedProvider === PROVIDER_CLOUD
            ? cloudProvider
            : selectedProvider === PROVIDER_OPENAI_COMPAT
                ? 'openai'
                : 'ollama';

        const settingsBody = { llm_provider: providerName };

        if (selectedProvider === PROVIDER_OLLAMA) {
            settingsBody.llm_base_url = providerUrl || 'http://host.docker.internal:11434';
        } else if (selectedProvider === PROVIDER_OPENAI_COMPAT && providerUrl) {
            settingsBody.llm_base_url = providerUrl;
        }
        if (providerApiKey) {
            settingsBody.llm_api_key = providerApiKey;
        }

        try {
            const settingsRes = await fetch('/api/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                body: JSON.stringify(settingsBody),
            });
            if (!settingsRes.ok) {
                const data = await settingsRes.json().catch(() => ({}));
                setProviderError(data.error || 'Failed to save provider settings');
                return;
            }

            // Probe the connection by listing models
            const modelsRes = await fetch('/api/models');
            const modelsData = await modelsRes.json().catch(() => ({}));
            if (!modelsRes.ok) {
                setProviderError(modelsData.message || 'Could not connect to provider');
                return;
            }

            // Cache probe results so step 2 doesn't re-fetch
            setAllModels(modelsData.models || []);
            setVisionModels([]);
            setStep((s) => s + 1);
        } catch (err) {
            setProviderError(err.message);
        } finally {
            setProviderSaving(false);
        }
    }, [selectedProvider, cloudProvider, providerUrl, providerApiKey]);

    // ── Final save: mark setup complete ─────────────────────────────
    const handleFinish = useCallback(async () => {
        setSaving(true);
        setError(null);
        try {
            const setModelRes = await fetch('/api/profiles/set-model', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                body: JSON.stringify({ model: selectedMain }),
            });
            if (!setModelRes.ok) {
                const data = await setModelRes.json().catch(() => ({}));
                throw new Error(data.error || 'Failed to set model on profiles');
            }

            const res = await fetch('/api/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                body: JSON.stringify({
                    setup_complete: true,
                    default_agent: 'computron',
                    vision_model: selectedVision,
                    compaction_model: selectedMain,
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
    }, [selectedMain, selectedVision, onComplete]);

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
            // Reset so re-probe in step 1 repopulates models
            setAllModels([]);
            setVisionModels([]);
            setSelectedMain(null);
            setModelsError(null);
        }
        if (step === 3) {
            setVisionModels([]);
            setSelectedVision(undefined);
            setModelsError(null);
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

                        <fieldset className={styles.providerFieldset}>
                            <legend className={styles.srOnly}>LLM Provider</legend>
                            <div className={styles.providerTiles}>
                                {[
                                    {
                                        key: PROVIDER_OLLAMA,
                                        name: 'Ollama (local)',
                                        desc: 'Run models on your own machine',
                                    },
                                    {
                                        key: PROVIDER_OPENAI_COMPAT,
                                        name: 'OpenAI-compatible endpoint',
                                        desc: 'LM Studio, vLLM, Groq, Together AI, and others',
                                    },
                                    {
                                        key: PROVIDER_CLOUD,
                                        name: 'Cloud API',
                                        desc: 'Anthropic or OpenAI cloud',
                                    },
                                ].map(({ key, name, desc }) => (
                                    <label
                                        key={key}
                                        className={`${styles.providerTile} ${selectedProvider === key ? styles.providerTileSelected : ''}`}
                                    >
                                        <input
                                            type="radio"
                                            name="provider"
                                            value={key}
                                            checked={selectedProvider === key}
                                            onChange={() => { setSelectedProvider(key); setProviderError(null); }}
                                            className={styles.providerTileInput}
                                        />
                                        <span className={styles.providerTileMarker} aria-hidden="true" />
                                        <span className={styles.providerTileText}>
                                            <span className={styles.providerTileName}>{name}</span>
                                            <span className={styles.providerTileDesc}>{desc}</span>
                                        </span>
                                    </label>
                                ))}
                            </div>
                        </fieldset>

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
                        {modelsError ? (
                            <ModelsErrorPanel
                                key={modelsError.message}
                                error={modelsError}
                                onRetry={retryFetch}
                                loading={modelsLoading}
                                selectedProvider={selectedProvider}
                            />
                        ) : modelsLoading ? (
                            <p className={styles.hint}>Loading models…</p>
                        ) : (
                            <div className={styles.modelList}>
                                {allModels.map((m) => (
                                    <ModelCard
                                        key={m.name}
                                        model={m}
                                        selected={selectedMain === m.name}
                                        onSelect={setSelectedMain}
                                    />
                                ))}
                            </div>
                        )}
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
                            Used for understanding images and screenshots. This can be a
                            smaller model since it only processes images.
                        </p>

                        {selectedProvider === PROVIDER_CLOUD ? (
                            <div className={styles.infoPanel} role="note">
                                Your cloud provider handles vision natively — no separate
                                vision model is needed.
                            </div>
                        ) : modelsError ? (
                            <ModelsErrorPanel
                                key={modelsError.message}
                                error={modelsError}
                                onRetry={retryFetch}
                                loading={modelsLoading}
                                selectedProvider={selectedProvider}
                            />
                        ) : modelsLoading ? (
                            <p className={styles.hint}>Loading models…</p>
                        ) : (
                            <div className={styles.modelList}>
                                {visionModels.map((m) => (
                                    <ModelCard
                                        key={m.name}
                                        model={m}
                                        selected={selectedVision === m.name}
                                        onSelect={setSelectedVision}
                                    />
                                ))}
                            </div>
                        )}

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
