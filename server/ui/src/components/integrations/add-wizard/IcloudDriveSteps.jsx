import Button from '../../primitives/Button.jsx';
import Callout from '../../primitives/Callout.jsx';
import styles from './add-wizard.module.css';
import { errorCopy } from './providers.js';
import { Stepper } from './SharedSteps.jsx';

// iCloud Drive has no app-specific-password option, so connecting it needs a
// live Apple ID sign-in plus a one-time 2FA code. Three steps: explain →
// credentials (triggers the code) → enter code (verifies + saves).

export function IcloudDriveExplainerStep({ provider, onBack, onNext }) {
    return (
        <>
            <Stepper step={1} />
            <div className={styles.wzBody}>
                <h2 className={styles.wzTitle}>Connect {provider.title}</h2>
                <p className={styles.wzSubtitle}>
                    You'll sign in with your <strong>Apple ID</strong> and a one-time
                    {' '}two-factor code. Computron stores the resulting trust token so it
                    {' '}doesn't have to ask for a code again.
                </p>
                <div className={styles.wzContent}>
                    <Callout
                        tone="info"
                        description="Use your Apple ID account password — not an app-specific password. Two-factor authentication must be enabled."
                    />
                    <div className={styles.chipStack}>
                        <span className={styles.chip}><i className="bi bi-check2" /> Encrypted at rest</span>
                        <span className={styles.chip}><i className="bi bi-check2" /> Agent never reads the credentials</span>
                        <span className={styles.chip}><i className="bi bi-check2" /> Revocable from your Apple ID at any time</span>
                    </div>
                </div>
            </div>
            <div className={styles.footer}>
                <Button onClick={onBack}>
                    <i className="bi bi-arrow-left" /> Back
                </Button>
                <div className={styles.footerRight}>
                    <Button variant="filled" onClick={onNext} data-testid="wizard-next">
                        Next <i className="bi bi-arrow-right" />
                    </Button>
                </div>
            </div>
        </>
    );
}

export function IcloudDriveCredentialsStep({
    provider, form, setForm, error, submitting, onBack, onCancel, onSubmit,
}) {
    const access = form.permissions.drive || 'r';
    const canSubmit = !submitting && form.email.trim() && form.password.trim();
    return (
        <>
            <Stepper step={2} />
            <div className={styles.wzBodyLeft}>
                <h2 className={styles.wzTitle}>Sign in to Apple</h2>
                <p className={styles.wzSubtitle}>
                    Apple will send a 6-digit code to your trusted devices when you continue.
                </p>
                <div className={styles.wzContent}>
                    <div className={styles.field}>
                        <label className={styles.fieldLabel}>Apple ID email</label>
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
                        <label className={styles.fieldLabel}>Apple ID password</label>
                        <input
                            className={styles.input}
                            type="password"
                            placeholder="Your Apple ID password"
                            value={form.password}
                            onChange={(e) => setForm(f => ({ ...f, password: e.target.value }))}
                            data-testid="wizard-password"
                        />
                    </div>
                    <div className={styles.field}>
                        <label className={styles.fieldLabel}>Label (optional)</label>
                        <input
                            className={styles.input}
                            placeholder={`${provider.title} · ${form.email || 'your Apple ID'}`}
                            value={form.label}
                            onChange={(e) => setForm(f => ({ ...f, label: e.target.value }))}
                        />
                    </div>
                    <div className={styles.subsectionLabel}>Permissions</div>
                    <div className={styles.permStack}>
                        <div className={styles.permRow}>
                            <span className={styles.permLabel}>Drive</span>
                            <select
                                className={styles.accessSelect}
                                value={access}
                                onChange={(e) => setForm(f => ({
                                    ...f, permissions: { ...f.permissions, drive: e.target.value },
                                }))}
                                data-testid="wizard-perm-drive"
                            >
                                <option value="r">Read only</option>
                                <option value="rw">Read + Write</option>
                            </select>
                        </div>
                    </div>
                    <Callout tone="info" description="You can change this later — no need to reconnect." />
                    {error && (() => {
                        const copy = errorCopy(error, provider);
                        return <Callout tone="danger" title={copy.title} description={copy.description} />;
                    })()}
                </div>
            </div>
            <div className={styles.footer}>
                <Button onClick={onBack} disabled={submitting}>
                    <i className="bi bi-arrow-left" /> Back
                </Button>
                <div className={styles.footerRight}>
                    <Button onClick={onCancel} disabled={submitting}>Cancel</Button>
                    <Button
                        variant="filled"
                        disabled={!canSubmit}
                        onClick={onSubmit}
                        data-testid="wizard-submit"
                    >
                        {submitting ? 'Sending code…' : <>Send code <i className="bi bi-send" /></>}
                    </Button>
                </div>
            </div>
        </>
    );
}

export function IcloudDriveTwoFactorStep({
    provider, form, twoFactor, setTwoFactor, error, submitting, onBack, onCancel, onSubmit,
}) {
    const code = twoFactor.code || '';
    const canSubmit = !submitting && code.trim().length >= 6;
    return (
        <>
            <Stepper step={3} />
            <div className={styles.wzBodyLeft}>
                <h2 className={styles.wzTitle}>Enter the 2FA code</h2>
                <p className={styles.wzSubtitle}>
                    Check your Apple devices for a 6-digit verification code and enter it below.
                </p>
                <div className={styles.wzContent}>
                    <div className={styles.field}>
                        <label className={styles.fieldLabel}>Verification code</label>
                        <input
                            className={`${styles.input} ${styles.inputMono}`}
                            inputMode="numeric"
                            autoComplete="one-time-code"
                            maxLength={8}
                            placeholder="123456"
                            value={code}
                            onChange={(e) => setTwoFactor(t => ({
                                ...t, code: e.target.value.replace(/\D/g, ''),
                            }))}
                            data-testid="wizard-2fa-code"
                        />
                        <span className={styles.fieldHint}>
                            Connecting as {form.email || 'your Apple ID'}.
                        </span>
                    </div>
                    {submitting && (
                        <div className={styles.checkList}>
                            <div className={styles.checkRow}>
                                <div className={`${styles.checkIcon} ${styles.running}`}>
                                    <span className={styles.spinner} />
                                </div>
                                <div className={styles.checkLabel}>Verifying and connecting…</div>
                                <div className={styles.checkMeta}>…</div>
                            </div>
                        </div>
                    )}
                    {error && (() => {
                        const copy = errorCopy(error, provider);
                        return <Callout tone="danger" title={copy.title} description={copy.description} />;
                    })()}
                </div>
            </div>
            <div className={styles.footer}>
                <Button onClick={onBack} disabled={submitting}>
                    <i className="bi bi-arrow-left" /> Back
                </Button>
                <div className={styles.footerRight}>
                    <Button onClick={onCancel} disabled={submitting}>Cancel</Button>
                    <Button
                        variant="filled"
                        disabled={!canSubmit}
                        onClick={onSubmit}
                        data-testid="wizard-2fa-submit"
                    >
                        {submitting ? 'Connecting…' : <>Connect <i className="bi bi-shield-check" /></>}
                    </Button>
                </div>
            </div>
        </>
    );
}
