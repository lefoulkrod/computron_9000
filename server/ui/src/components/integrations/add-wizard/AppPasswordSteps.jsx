import Button from '../../primitives/Button.jsx';
import Callout from '../../primitives/Callout.jsx';
import styles from './add-wizard.module.css';
import { errorCopy } from './providers.js';
import { Stepper } from './SharedSteps.jsx';

export function ExplainerStep({ provider, onBack, onNext }) {
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

export function CredentialsStep({ provider, form, setForm, error, onBack, onCancel, onSubmit }) {
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
                    <Callout
                        tone="info"
                        description="You can change this later — no need to reconnect."
                    />

                    {error && (() => {
                        const copy = errorCopy(error, provider);
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

export function VerifyingStep() {
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
