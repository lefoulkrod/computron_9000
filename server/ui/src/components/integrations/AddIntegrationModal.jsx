import { useEffect, useState } from 'react';

import Button from '../primitives/Button.jsx';
import Callout from '../primitives/Callout.jsx';
import styles from './AddIntegrationModal.module.css';

// Map supervisor/route error shapes to user-facing Callout copy. Rendered
// next to the action that triggered the failure; the user reads this and
// decides what to fix, so the wording is intentionally about *their*
// next move, not about what the broker / supervisor saw.
function _errorCopy(error, provider) {
    const vendor = provider?.vendor ?? provider?.title ?? 'this provider';
    switch (error?.code) {
        case 'AUTH':
            return {
                title: `${vendor} rejected the password`,
                description:
                    'App-specific passwords sometimes get revoked or mistyped. ' +
                    `Generate a fresh one in ${vendor}, paste it again, and retry.`,
            };
        case 'UPSTREAM':
            return {
                title: `Couldn't reach ${vendor}`,
                description:
                    'The server returned an error or timed out. Try again in a moment — ' +
                    'if it keeps failing, check your network or the provider\'s status page.',
            };
        case 'BAD_REQUEST':
            return {
                title: 'Couldn\'t add this integration',
                description: error.message || 'The request was rejected. Double-check your inputs.',
            };
        case 'NETWORK':
            return {
                title: 'Network error',
                description: error.message || 'Check your connection and try again.',
            };
        default:
            return {
                title: 'Couldn\'t add this integration',
                description: error?.message || 'Try again, or refresh and start over.',
            };
    }
}

const PROVIDERS = [
    {
        slug: 'icloud',
        category: 'Email, Calendar & Storage',
        title: 'iCloud',
        description: 'Email, calendar, and iCloud Drive · app password',
        icon: 'bi-cloud',
        vendor: 'Apple',
        appPasswordUrl: 'https://account.apple.com/account/manage',
        appPasswordHost: 'account.apple.com',
        emailPlaceholder: 'you@icloud.com',
        capabilities: [
            { key: 'email_calendar', label: 'Email & Calendar', icon: 'bi-envelope-at', desc: 'Read/search email, view calendar events' },
            { key: 'storage', label: 'iCloud Drive', icon: 'bi-cloud-arrow-up', desc: 'Browse, download, and upload files' },
        ],
    },
    {
        slug: 'gmail',
        category: 'Email',
        title: 'Gmail',
        description: 'Email · app password',
        icon: 'bi-envelope-at',
        vendor: 'Google',
        appPasswordUrl: 'https://myaccount.google.com/apppasswords',
        appPasswordHost: 'myaccount.google.com',
        emailPlaceholder: 'you@gmail.com',
        capabilities: [
            { key: 'email_calendar', label: 'Email', icon: 'bi-envelope-at', desc: 'Read/search email' },
        ],
    },
];

export default function AddIntegrationModal({ onClose, onAdded }) {
    const [provider, setProvider] = useState(null);
    const [step, setStep] = useState(1);
    const [form, setForm] = useState({
        email: '',
        password: '',
        label: '',
        writeAllowed: false,
        enabledCapabilities: [],
    });
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState(null);
    const [result, setResult] = useState(null);

    useEffect(() => {
        const onEsc = (e) => {
            if (e.key === 'Escape' && !submitting) onClose();
        };
        document.addEventListener('keydown', onEsc);
        return () => document.removeEventListener('keydown', onEsc);
    }, [onClose, submitting]);

    const handleBackdrop = (e) => {
        if (e.target === e.currentTarget && !submitting) onClose();
    };

    const handleSubmit = async () => {
        setSubmitting(true);
        setError(null);
        setStep(3);
        const email = form.email.trim();
        const label = form.label.trim() || `${provider.title} · ${email}`;
        try {
            const resp = await fetch('/api/integrations', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    slug: provider.slug,
                    label,
                    auth_blob: {
                        email,
                        password: form.password.replace(/\s+/g, ''),
                    },
                    write_allowed: form.writeAllowed,
                    enabled_capabilities: form.enabledCapabilities,
                }),
            });
            const body = await resp.json().catch(() => ({}));
            if (!resp.ok) {
                setError({
                    code: body?.error?.code || 'ERROR',
                    message: body?.error?.message || `HTTP ${resp.status}`,
                });
                setSubmitting(false);
                setStep(2);
                return;
            }
            setResult(body);
            setSubmitting(false);
        } catch (err) {
            setError({
                code: 'NETWORK',
                message: err?.message || 'Request failed',
            });
            setSubmitting(false);
            setStep(2);
        }
    };

    return (
        <div className={styles.backdrop} onClick={handleBackdrop}>
            <div className={styles.modal} role="dialog" aria-modal="true">
                <div className={styles.header}>
                    <div className={styles.title}>ADD INTEGRATION</div>
                    <button
                        className={styles.closeBtn}
                        onClick={onClose}
                        disabled={submitting}
                        aria-label="Close"
                    >
                        <i className="bi bi-x-lg" />
                    </button>
                </div>

                {!provider ? (
                    <ProviderPicker
                        onPick={(p) => {
                            setProvider(p);
                            setStep(1);
                            setForm(f => ({
                                ...f,
                                enabledCapabilities: (p.capabilities || []).map(c => c.key),
                            }));
                        }}
                        onCancel={onClose}
                    />
                ) : result ? (
                    <SuccessScreen
                        provider={provider}
                        form={form}
                        result={result}
                        onAddAnother={() => {
                            setProvider(null);
                            setResult(null);
                            setStep(1);
                            setForm({
                                email: '', password: '', label: '', writeAllowed: false, enabledCapabilities: [],
                            });
                        }}
                        onDone={() => { onAdded?.(); }}
                    />
                ) : step === 1 ? (
                    <ExplainerStep
                        provider={provider}
                        onBack={() => setProvider(null)}
                        onNext={() => setStep(2)}
                    />
                ) : step === 2 ? (
                    <CredentialsStep
                        provider={provider}
                        form={form}
                        setForm={setForm}
                        error={error}
                        onBack={() => setStep(1)}
                        onCancel={onClose}
                        onSubmit={handleSubmit}
                    />
                ) : (
                    <VerifyingStep />
                )}
            </div>
        </div>
    );
}

function ProviderPicker({ onPick, onCancel }) {
    const categories = PROVIDERS.reduce((acc, p) => {
        acc[p.category] = acc[p.category] || [];
        acc[p.category].push(p);
        return acc;
    }, {});

    return (
        <>
            <div className={styles.body}>
                {Object.entries(categories).map(([category, items]) => (
                    <div key={category} className={styles.pickerGroup}>
                        <div className={styles.groupLabel}>{category}</div>
                        <div className={styles.providerGrid}>
                            {items.map(p => (
                                <button
                                    key={p.slug}
                                    className={styles.providerCard}
                                    onClick={() => onPick(p)}
                                    data-testid={`provider-${p.slug}`}
                                >
                                    <div className={styles.providerIcon}>
                                        <i className={`bi ${p.icon}`} />
                                    </div>
                                    <div className={styles.providerInfo}>
                                        <div className={styles.providerTitle}>{p.title}</div>
                                        <div className={styles.providerDesc}>{p.description}</div>
                                    </div>
                                    <i className={`bi bi-chevron-right ${styles.providerChev}`} />
                                </button>
                            ))}
                        </div>
                    </div>
                ))}
            </div>
            <div className={styles.footer}>
                <Button onClick={onCancel}>Cancel</Button>
            </div>
        </>
    );
}

function Stepper({ step }) {
    const circleClass = (n) => {
        if (step > n) return styles.done;
        if (step === n) return styles.active;
        return '';
    };
    const lineClass = (n) => (step > n ? styles.done : '');
    const circleContent = (n) => (step > n ? <i className="bi bi-check-lg" /> : n);
    return (
        <div className={styles.stepper}>
            <div className={`${styles.stepCircle} ${circleClass(1)}`}>{circleContent(1)}</div>
            <div className={`${styles.stepLine} ${lineClass(1)}`} />
            <div className={`${styles.stepCircle} ${circleClass(2)}`}>{circleContent(2)}</div>
            <div className={`${styles.stepLine} ${lineClass(2)}`} />
            <div className={`${styles.stepCircle} ${circleClass(3)}`}>{circleContent(3)}</div>
        </div>
    );
}

function ExplainerStep({ provider, onBack, onNext }) {
    return (
        <>
            <Stepper step={1} />
            <div className={styles.wzBody}>
                <h2 className={styles.wzTitle}>Connect {provider.title}</h2>
                <p className={styles.wzSubtitle}>
                    You'll generate an <strong>app-specific password</strong> — a credential
                    {' '}{provider.vendor} issues specifically for third-party apps, separate
                    from your main account password.
                </p>
                <div className={styles.wzContent}>
                    <Callout
                        tone="info"
                        description={`Requires a ${provider.vendor} account with two-factor authentication enabled.`}
                    />
                    <div className={styles.chipStack}>
                        <span className={styles.chip}><i className="bi bi-check2" /> Encrypted at rest</span>
                        <span className={styles.chip}><i className="bi bi-check2" /> Agent never reads the password</span>
                        <span className={styles.chip}><i className="bi bi-check2" /> Revocable from {provider.vendor} at any time</span>
                    </div>
                </div>
            </div>
            <div className={styles.footer}>
                <Button onClick={onBack}>
                    <i className="bi bi-arrow-left" /> Back
                </Button>
                <div className={styles.footerRight}>
                    <Button
                        variant="filled"
                        onClick={onNext}
                        data-testid="wizard-next"
                    >
                        Next <i className="bi bi-arrow-right" />
                    </Button>
                </div>
            </div>
        </>
    );
}

function CredentialsStep({ provider, form, setForm, error, onBack, onCancel, onSubmit }) {
    const canSubmit = form.email.trim() && form.password.trim();
    return (
        <>
            <Stepper step={2} />
            <div className={styles.wzBodyLeft}>
                <h2 className={styles.wzTitle}>Generate &amp; paste</h2>
                <p className={styles.wzSubtitle}>
                    Create an app-specific password in your {provider.vendor} account
                    settings, name it "Computron," and paste it below.
                </p>
                <div className={styles.wzContent}>
                    <a
                        className={styles.linkBtn}
                        href={provider.appPasswordUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                    >
                        <span>
                            <i className="bi bi-box-arrow-up-right" /> Open {provider.vendor} app-passwords page
                        </span>
                        <span className={styles.linkBtnHint}>{provider.appPasswordHost}</span>
                    </a>

                    <div className={styles.field}>
                        <label className={styles.fieldLabel}>{provider.vendor} email</label>
                        <input
                            className={styles.input}
                            type="email"
                            placeholder={provider.emailPlaceholder}
                            value={form.email}
                            onChange={(e) => setForm(f => ({ ...f, email: e.target.value }))}
                            data-testid="wizard-email"
                        />
                    </div>

                    <div className={styles.field}>
                        <label className={styles.fieldLabel}>App-specific password</label>
                        <input
                            className={`${styles.input} ${styles.inputMono}`}
                            type="password"
                            placeholder="xxxx-xxxx-xxxx-xxxx"
                            value={form.password}
                            onChange={(e) => setForm(f => ({ ...f, password: e.target.value }))}
                            data-testid="wizard-password"
                        />
                        <span className={styles.fieldHint}>
                            Pasted verbatim from {provider.vendor} — spaces are trimmed automatically.
                        </span>
                    </div>

                    <div className={styles.field}>
                        <label className={styles.fieldLabel}>Label (optional)</label>
                        <input
                            className={styles.input}
                            placeholder={`${provider.title} · ${form.email || 'your email'}`}
                            value={form.label}
                            onChange={(e) => setForm(f => ({ ...f, label: e.target.value }))}
                        />
                        <span className={styles.fieldHint}>
                            How this integration appears in your list.
                        </span>
                    </div>

                    <div className={styles.subsectionLabel}>Permissions</div>
                    <div className={styles.radioStack}>
                        <label className={`${styles.radioCard} ${!form.writeAllowed ? styles.selected : ''}`}>
                            <input
                                type="radio"
                                className={styles.radioInput}
                                checked={!form.writeAllowed}
                                onChange={() => setForm(f => ({ ...f, writeAllowed: false }))}
                            />
                            <div className={styles.radioIndicator} />
                            <div className={styles.radioInfo}>
                                <div className={styles.radioTitle}>Read only</div>
                                <div className={styles.radioDesc}>
                                    Search email, read messages, view your calendar.
                                </div>
                            </div>
                        </label>
                        <label className={`${styles.radioCard} ${form.writeAllowed ? styles.selected : ''}`}>
                            <input
                                type="radio"
                                className={styles.radioInput}
                                checked={form.writeAllowed}
                                onChange={() => setForm(f => ({ ...f, writeAllowed: true }))}
                            />
                            <div className={styles.radioIndicator} />
                            <div className={styles.radioInfo}>
                                <div className={styles.radioTitle}>Read and write</div>
                                <div className={styles.radioDesc}>
                                    All of the above, plus send and move email, and create or
                                    delete calendar events.
                                </div>
                            </div>
                        </label>
                    </div>
                    {provider.capabilities && provider.capabilities.length > 1 && (
                        <>
                            <div className={styles.subsectionLabel}>Services to enable</div>
                            <div className={styles.checkStack}>
                                {provider.capabilities.map(cap => (
                                    <label key={cap.key} className={styles.checkRow}>
                                        <input
                                            type="checkbox"
                                            checked={form.enabledCapabilities.includes(cap.key)}
                                            onChange={(e) => {
                                                setForm(f => ({
                                                    ...f,
                                                    enabledCapabilities: e.target.checked
                                                        ? [...f.enabledCapabilities, cap.key]
                                                        : f.enabledCapabilities.filter(k => k !== cap.key),
                                                }));
                                            }}
                                        />
                                        <span className={styles.checkLabel}>
                                            <i className={`bi ${cap.icon}`} /> {cap.label}
                                        </span>
                                        <span className={styles.checkHelp}>{cap.desc}</span>
                                    </label>
                                ))}
                            </div>
                        </>
                    )}
                    <Callout
                        tone="info"
                        description="You can change this later — no need to reconnect."
                    />

                    {error && (() => {
                        const copy = _errorCopy(error, provider);
                        return (
                            <Callout
                                tone="danger"
                                title={copy.title}
                                description={copy.description}
                            />
                        );
                    })()}
                </div>
            </div>
            <div className={styles.footer}>
                <Button onClick={onBack}>
                    <i className="bi bi-arrow-left" /> Back
                </Button>
                <div className={styles.footerRight}>
                    <Button onClick={onCancel}>Cancel</Button>
                    <Button
                        variant="filled"
                        disabled={!canSubmit}
                        onClick={onSubmit}
                        data-testid="wizard-submit"
                    >
                        Verify &amp; save <i className="bi bi-shield-check" />
                    </Button>
                </div>
            </div>
        </>
    );
}

function VerifyingStep() {
    return (
        <>
            <Stepper step={3} />
            <div className={styles.wzBodyLeft}>
                <h2 className={styles.wzTitle}>Connecting…</h2>
                <p className={styles.wzSubtitle}>This usually takes a few seconds.</p>
                <div className={styles.wzContent}>
                    <div className={styles.checkList}>
                        <div className={styles.checkRow}>
                            <div className={`${styles.checkIcon} ${styles.done}`}>
                                <i className="bi bi-check-circle-fill" />
                            </div>
                            <div className={styles.checkLabel}>Securing your credentials</div>
                            <div className={styles.checkMeta}>done</div>
                        </div>
                        <div className={styles.checkRow}>
                            <div className={`${styles.checkIcon} ${styles.running}`}>
                                <span className={styles.spinner} />
                            </div>
                            <div className={styles.checkLabel}>Signing in to your email</div>
                            <div className={styles.checkMeta}>…</div>
                        </div>
                    </div>
                </div>
            </div>
            <div className={styles.footer}>
                <Button disabled>
                    <i className="bi bi-arrow-left" /> Back
                </Button>
                <div className={styles.footerRight}>
                    <Button disabled>Cancel</Button>
                    <Button variant="filled" disabled>Continue</Button>
                </div>
            </div>
        </>
    );
}

function SuccessScreen({ provider, form, result, onAddAnother, onDone }) {
    const enabledLabels = (provider.capabilities || [])
        .filter(c => (result.capabilities || []).includes(c.key))
        .map(c => c.label);
    const what = enabledLabels.length > 0 
        ? enabledLabels.join(' and ').toLowerCase()
        : 'your data';
    return (
        <>
            <Stepper step={4} />
            <div className={styles.wzBodyLeft}>
                <h2 className={styles.wzTitle}>{provider.title} connected</h2>
                <p className={styles.wzSubtitle}>
                    Your agent can now access {what}.
                </p>
                <div className={styles.wzContent}>
                    <table className={styles.kvTable}>
                        <tbody>
                            <tr>
                                <td>ID</td>
                                <td>{result.id}</td>
                            </tr>
                            <tr>
                                <td>Account</td>
                                <td>{form.email}</td>
                            </tr>
                            <tr>
                                <td>Label</td>
                                <td>{form.label || `${provider.title} · ${form.email}`}</td>
                            </tr>
                            <tr>
                                <td>Permissions</td>
                                <td>{form.writeAllowed ? 'Read and write' : 'Read only'}</td>
                            </tr>
                            <tr>
                                <td>Enabled services</td>
                                <td>{enabledLabels.length > 0 ? enabledLabels.join(' · ') : '—'}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
            <div className={styles.footer}>
                <div className={styles.footerRight}>
                    <Button onClick={onAddAnother}>
                        <i className="bi bi-plus-lg" /> Add another
                    </Button>
                    <Button
                        variant="filled"
                        onClick={onDone}
                        data-testid="wizard-done"
                    >
                        Done
                    </Button>
                </div>
            </div>
        </>
    );
}
