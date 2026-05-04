import Button from '../../primitives/Button.jsx';
import Callout from '../../primitives/Callout.jsx';
import styles from './add-wizard.module.css';
import { errorCopy } from './providers.js';
import { Stepper } from './SharedSteps.jsx';

export function OauthCapabilitiesStep({
    provider, oauth, setOauth, form, setForm, onBack, onNext,
}) {
    const anyCapability = Object.values(oauth.capabilities).some(Boolean);
    const canContinue = anyCapability && form.email.trim();
    return (
        <>
            <Stepper step={1} />
            <div className={styles.wzBodyLeft}>
                <h2 className={styles.wzTitle}>Connect {provider.title}</h2>
                <p className={styles.wzSubtitle}>
                    Computron uses your own Google OAuth credentials — no
                    shared app, no third-party servers. The next screen
                    walks you through a one-time ~5 minute setup in Google
                    Cloud Console.
                </p>
                <div className={styles.wzContent}>
                    <div className={styles.field}>
                        <label className={styles.fieldLabel}>Account email</label>
                        <input
                            className={styles.input}
                            type="email"
                            placeholder="you@gmail.com"
                            value={form.email}
                            onChange={(e) => setForm(f => ({ ...f, email: e.target.value }))}
                            data-testid="wizard-email"
                        />
                        <span className={styles.fieldHint}>
                            The Google account you'll sign in with.
                        </span>
                    </div>

                    <div className={styles.subsectionLabel}>What to share</div>
                    <div className={styles.radioStack}>
                        {provider.capabilityGroups.map(g => (
                            <div
                                key={g.id}
                                className={`${styles.radioCard} ${oauth.capabilities[g.id] ? styles.selected : ''}`}
                            >
                                <label className={styles.capLabel}>
                                    <input
                                        type="checkbox"
                                        className={styles.radioInput}
                                        checked={!!oauth.capabilities[g.id]}
                                        onChange={(e) => setOauth(o => ({
                                            ...o,
                                            capabilities: {
                                                ...o.capabilities,
                                                [g.id]: e.target.checked,
                                            },
                                        }))}
                                        data-testid={`oauth-capability-${g.id}`}
                                    />
                                    <div className={styles.radioIndicator} />
                                    <div className={styles.radioInfo}>
                                        <div className={styles.radioTitle}>{g.label}</div>
                                        <div className={styles.radioDesc}>{g.description}</div>
                                    </div>
                                </label>
                                <select
                                    className={styles.accessSelect}
                                    value={oauth.access[g.id] || 'r'}
                                    onChange={(e) => setOauth(o => ({
                                        ...o,
                                        access: { ...o.access, [g.id]: e.target.value },
                                    }))}
                                    disabled={!oauth.capabilities[g.id] || !g.writeScopes?.length}
                                    data-testid={`oauth-access-${g.id}`}
                                >
                                    <option value="r">Read only</option>
                                    <option value="rw" disabled={!g.writeScopes?.length}>
                                        Read + Write
                                    </option>
                                </select>
                            </div>
                        ))}
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
                        disabled={!canContinue}
                        data-testid="wizard-next"
                    >
                        Continue <i className="bi bi-arrow-right" />
                    </Button>
                </div>
            </div>
        </>
    );
}

export function OauthGcpSetupStep({
    provider, oauth, setOauth, error, submitting, onBack, onCancel, onSubmit,
}) {
    const canSubmit = (
        oauth.clientId.trim() && oauth.clientSecret.trim() && !submitting
    );
    return (
        <>
            <Stepper step={2} />
            <div className={styles.wzBodyLeft}>
                <h2 className={styles.wzTitle}>Get your OAuth credentials</h2>
                <p className={styles.wzSubtitle}>
                    Set up a one-person OAuth client in Google Cloud (~5
                    minutes) and paste the credentials below.
                </p>
                <div className={styles.wzContent}>
                    <details className={styles.gcpStep}>
                        <summary>1. Create a Google Cloud project</summary>
                        <div className={styles.gcpStepBody}>
                            <a
                                className={styles.linkBtn}
                                href="https://console.cloud.google.com"
                                target="_blank"
                                rel="noopener noreferrer"
                            >
                                <span>
                                    <i className="bi bi-box-arrow-up-right" /> Open Google Cloud Console
                                </span>
                                <span className={styles.linkBtnHint}>console.cloud.google.com</span>
                            </a>
                            <p>
                                Click the project dropdown at the top, then
                                <strong> New Project</strong>. Name it anything
                                you'll recognize. Defaults are fine for the rest.
                            </p>
                        </div>
                    </details>

                    <details className={styles.gcpStep}>
                        <summary>2. Enable the APIs</summary>
                        <div className={styles.gcpStepBody}>
                            <p>
                                In the side menu: <strong>APIs &amp; Services → Library</strong>.
                                Search and enable each of:
                            </p>
                            <ul>
                                <li>Gmail API</li>
                                <li>Google Calendar API</li>
                                <li>Google Drive API</li>
                                <li>People API</li>
                            </ul>
                        </div>
                    </details>

                    <details className={styles.gcpStep}>
                        <summary>3. Set up the Google Auth Platform</summary>
                        <div className={styles.gcpStepBody}>
                            <a
                                className={styles.linkBtn}
                                href="https://console.cloud.google.com/auth/overview"
                                target="_blank"
                                rel="noopener noreferrer"
                            >
                                <span>
                                    <i className="bi bi-box-arrow-up-right" /> Open Google Auth Platform
                                </span>
                                <span className={styles.linkBtnHint}>console.cloud.google.com/auth</span>
                            </a>
                            <p>
                                On first run you'll see a four-step
                                <strong> Create branding</strong> wizard:
                            </p>
                            <ul>
                                <li><strong>App Information:</strong> any name, your email as support contact.</li>
                                <li><strong>Audience:</strong> pick <strong>External</strong> (only option for personal Gmail).</li>
                                <li><strong>Contact Information:</strong> your email.</li>
                                <li><strong>Finish:</strong> agree to the Data Policy.</li>
                            </ul>
                        </div>
                    </details>

                    <details className={styles.gcpStep}>
                        <summary>4. Publish the app</summary>
                        <div className={styles.gcpStepBody}>
                            <p>
                                In the sidebar:
                                <strong> Audience → Publishing status → Publish app</strong>.
                                Confirm the prompt.
                            </p>
                            <p>
                                You'll see an <strong>"unverified app"</strong> warning later
                                during sign-in — that's expected and harmless. You're the
                                only user; Google's verification process is for apps with
                                external users, not for your own one-person app.
                            </p>
                            <p>
                                Why this step: in Testing mode the refresh token expires
                                after 7 days, which means Computron loses access weekly.
                                Publishing makes tokens long-lived.
                            </p>
                        </div>
                    </details>

                    <details className={styles.gcpStep}>
                        <summary>5. Create the OAuth client</summary>
                        <div className={styles.gcpStepBody}>
                            <p>
                                Still in Google Auth Platform: sidebar
                                <strong> Clients → + Create client</strong>.
                            </p>
                            <ul>
                                <li><strong>Application type:</strong> Desktop app ← Computron uses the loopback redirect flow that this client type enables.</li>
                                <li><strong>Name:</strong> anything.</li>
                            </ul>
                            <p>
                                Click <strong>Create</strong>. Google shows the Client ID
                                and Client Secret in a one-time dialog — copy both now,
                                you can't view the secret again. Paste below.
                            </p>
                        </div>
                    </details>

                    <div className={styles.field}>
                        <label className={styles.fieldLabel}>Client ID</label>
                        <input
                            className={`${styles.input} ${styles.inputMono}`}
                            placeholder="123456789-abc.apps.googleusercontent.com"
                            value={oauth.clientId}
                            onChange={(e) => setOauth(o => ({ ...o, clientId: e.target.value }))}
                            data-testid="oauth-client-id"
                        />
                    </div>

                    <div className={styles.field}>
                        <label className={styles.fieldLabel}>Client Secret</label>
                        <input
                            className={`${styles.input} ${styles.inputMono}`}
                            type="password"
                            placeholder="GOCSPX-..."
                            value={oauth.clientSecret}
                            onChange={(e) => setOauth(o => ({ ...o, clientSecret: e.target.value }))}
                            data-testid="oauth-client-secret"
                        />
                    </div>

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
                <Button onClick={onBack} disabled={submitting}>
                    <i className="bi bi-arrow-left" /> Back
                </Button>
                <div className={styles.footerRight}>
                    <Button onClick={onCancel} disabled={submitting}>
                        Cancel
                    </Button>
                    <Button
                        variant="filled"
                        disabled={!canSubmit}
                        onClick={onSubmit}
                        data-testid="oauth-authorize"
                    >
                        Authorize <i className="bi bi-shield-check" />
                    </Button>
                </div>
            </div>
        </>
    );
}

export function OauthRedirectStep({ provider, oauth, error, onCancel, onRestart }) {
    const status = oauth.status;
    const pending = oauth.pending;
    const authorizeUrl = pending?.authorize_url ?? '';
    const terminal = status && status !== 'pending';

    const reopenPopup = () => {
        if (!authorizeUrl) return;
        window.open(
            authorizeUrl, 'computron-google-oauth',
            'width=600,height=720',
        );
    };

    if (status === 'denied' || status === 'expired' || status === 'error') {
        const title = status === 'denied'
            ? 'Authorization was denied'
            : status === 'expired'
                ? 'Sign-in expired'
                : (error ? errorCopy(error, provider).title : 'Authorization failed');
        const description = status === 'denied'
            ? "You clicked 'Cancel' on Google's consent screen. Try again to retry."
            : status === 'expired'
                ? "The sign-in link timed out. Try again — they're short-lived."
                : (error ? errorCopy(error, provider).description : 'Try again.');
        return (
            <>
                <Stepper step={3} />
                <div className={styles.wzBodyLeft}>
                    <h2 className={styles.wzTitle}>Couldn't connect {provider.title}</h2>
                    <div className={styles.wzContent}>
                        <Callout tone="danger" title={title} description={description} />
                    </div>
                </div>
                <div className={styles.footer}>
                    <Button onClick={onRestart}>
                        <i className="bi bi-arrow-left" /> Try again
                    </Button>
                    <div className={styles.footerRight}>
                        <Button onClick={onCancel}>Cancel</Button>
                    </div>
                </div>
            </>
        );
    }

    return (
        <>
            <Stepper step={3} />
            <div className={styles.wzBodyLeft}>
                <h2 className={styles.wzTitle}>Authorize on Google</h2>
                <p className={styles.wzSubtitle}>
                    A Google sign-in window just opened in your browser.
                    Sign in with the account you want to connect, then
                    approve the requested permissions.
                </p>
                <div className={styles.wzContent}>
                    <div className={styles.checkRow}>
                        <span className={styles.spinner} />
                        <span>Waiting for you to sign in&hellip;</span>
                    </div>
                    <Callout
                        tone="info"
                        title={<>Seeing &ldquo;Google hasn&rsquo;t verified this app&rdquo;?</>}
                        description={<>
                            That&rsquo;s expected &mdash; this is your own personal OAuth app,
                            not a published one. Click <strong>Advanced</strong>, then{' '}
                            <strong>Go to &hellip; (unsafe)</strong> to continue.
                        </>}
                    />
                    <p className={styles.wzSubtitle}>
                        Did the popup get blocked or close accidentally?
                    </p>
                    <button
                        className={styles.linkBtn}
                        onClick={reopenPopup}
                        data-testid="oauth-reopen-popup"
                    >
                        <span>
                            <i className="bi bi-box-arrow-up-right" /> Reopen sign-in window
                        </span>
                    </button>
                </div>
            </div>
            <div className={styles.footer}>
                <Button onClick={onCancel} disabled={terminal}>
                    Cancel
                </Button>
            </div>
        </>
    );
}
