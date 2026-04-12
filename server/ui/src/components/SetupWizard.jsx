import { useState, useEffect, useCallback } from 'react';
import styles from './SetupWizard.module.css';

const STEPS = ['Welcome', 'Main Model', 'Vision Model', 'Ready'];

function ProgressBar({ currentStep }) {
    return (
        <div className={styles.progressBar}>
            {STEPS.map((label, i) => {
                const done = i < currentStep;
                const active = i === currentStep;
                return (
                    <div key={label} className={styles.progressStep}>
                        {i > 0 && (
                            <div className={`${styles.progressLine} ${done ? styles.progressLineDone : ''}`} />
                        )}
                        <div
                            className={`${styles.progressCircle} ${active ? styles.progressCircleActive : ''} ${done ? styles.progressCircleDone : ''}`}
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
        >
            <span className={`${styles.radio} ${selected ? styles.radioSelected : ''}`} />
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
                        <span className={`${styles.badge} ${styles.badgeCloud}`}>
                            cloud
                        </span>
                    )}
                    {(model.capabilities || []).includes('vision') && (
                        <span className={`${styles.badge} ${styles.badgeVision}`}>
                            vision
                        </span>
                    )}
                </div>
            </div>
        </button>
    );
}

function ModelsErrorPanel({ error, onRetry, loading }) {
    return (
        <div className={styles.errorPanel}>
            <div className={styles.errorTitle}>Can't reach Ollama</div>
            <div className={styles.errorMessage}>{error.message}</div>
            {error.llmHost && (
                <div className={styles.errorDetail}>
                    Trying: <code>{error.llmHost}</code>
                </div>
            )}
            <ul className={styles.errorHints}>
                <li>Make sure Ollama is running on the host (<code>ollama serve</code>).</li>
                <li>
                    On macOS / Windows / WSL2, pass{' '}
                    <code>-e LLM_HOST=http://host.docker.internal:11434</code> when starting
                    the container.
                </li>
                <li>
                    On Linux, make sure the container was started with{' '}
                    <code>--network=host</code>.
                </li>
            </ul>
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
    const [allModels, setAllModels] = useState([]);
    const [visionModels, setVisionModels] = useState([]);
    const [selectedMain, setSelectedMain] = useState(null);
    const [selectedVision, setSelectedVision] = useState(null);
    const [saving, setSaving] = useState(false);
    const [modelsError, setModelsError] = useState(null);
    const [modelsLoading, setModelsLoading] = useState(false);

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

    // Fetch all models when entering step 1 (list empty == not-yet-fetched or retry)
    useEffect(() => {
        if (step !== 1 || allModels.length > 0) return;
        fetchModels('/api/models', setAllModels);
    }, [step, allModels.length, fetchModels]);

    // Fetch vision models when entering step 2
    useEffect(() => {
        if (step !== 2 || visionModels.length > 0) return;
        fetchModels('/api/models?capability=vision', setVisionModels);
    }, [step, visionModels.length, fetchModels]);

    // Retry re-runs the fetch for the current step by clearing its list.
    const retryFetch = () => {
        setModelsError(null);
        if (step === 1) setAllModels([]);
        else if (step === 2) setVisionModels([]);
    };

    const [error, setError] = useState(null);

    const handleFinish = useCallback(async () => {
        setSaving(true);
        setError(null);
        try {
            // Set the picked model on all OOTB profiles that have no model
            const setModelRes = await fetch('/api/profiles/set-model', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: selectedMain }),
            });
            if (!setModelRes.ok) {
                const data = await setModelRes.json().catch(() => ({}));
                throw new Error(data.error || 'Failed to set model on profiles');
            }

            // Save settings
            const res = await fetch('/api/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
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
        (step === 1 && selectedMain) ||
        (step === 2 && selectedVision) ||
        step === 3;

    const buttonLabel =
        step === 0 ? 'Get Started'
            : step === 3 ? 'Start Chatting'
                : 'Continue';

    const handleNext = () => {
        if (step === 3) {
            handleFinish();
        } else {
            setStep((s) => s + 1);
        }
    };

    return (
        <div className={styles.overlay}>
            <div className={styles.card}>
                <ProgressBar currentStep={step} />

                {/* Step 0: Welcome */}
                {step === 0 && (
                    <div className={styles.stepContent}>
                        <h1 className={styles.title}>Welcome to Computron</h1>
                        <p className={styles.subtitle}>
                            Let's get you set up. We'll pick a main model and a vision model
                            so everything is ready to go.
                        </p>
                    </div>
                )}

                {/* Step 1: Main Model */}
                {step === 1 && (
                    <div className={styles.stepContent}>
                        <h1 className={styles.title}>Choose your main model</h1>
                        <p className={styles.subtitle}>
                            This will be set as the default model for all built-in agent profiles.
                            You can change individual profiles later in Settings &gt; Agent Profiles.
                        </p>
                        <p className={styles.hint}>Suggested: kimi-k2.5:cloud</p>
                        {modelsError ? (
                            <ModelsErrorPanel error={modelsError} onRetry={retryFetch} loading={modelsLoading} />
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

                {/* Step 2: Vision Model */}
                {step === 2 && (
                    <div className={styles.stepContent}>
                        <h1 className={styles.title}>Choose a vision model</h1>
                        <p className={styles.subtitle}>
                            Used for understanding images, screenshots, and visual content.
                            This can be a smaller model since it only processes images.
                        </p>
                        <p className={styles.hint}>Suggested: qwen3.5 — Filtered to models with vision capability</p>
                        {modelsError ? (
                            <ModelsErrorPanel error={modelsError} onRetry={retryFetch} loading={modelsLoading} />
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
                    </div>
                )}

                {/* Step 3: Ready */}
                {step === 3 && (
                    <div className={styles.stepContent}>
                        <div className={styles.stepIcon}>&#10003;</div>
                        <h1 className={styles.title}>You're all set</h1>
                        <div className={styles.summary}>
                            <div className={styles.summaryRow}>
                                <span className={styles.summaryLabel}>Main model</span>
                                <span className={styles.summaryValue}>{selectedMain}</span>
                            </div>
                            <div className={styles.summaryRow}>
                                <span className={styles.summaryLabel}>Vision model</span>
                                <span className={styles.summaryValue}>{selectedVision}</span>
                            </div>
                        </div>
                    </div>
                )}

                {error && (
                    <div className={styles.error}>{error}</div>
                )}

                {/* Navigation buttons */}
                <div className={styles.nav}>
                    {step > 0 && step < 3 && (
                        <button
                            className={styles.backBtn}
                            onClick={() => setStep((s) => s - 1)}
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
