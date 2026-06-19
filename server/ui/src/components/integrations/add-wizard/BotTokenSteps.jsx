import Button from '../../primitives/Button.jsx';
import Callout from '../../primitives/Callout.jsx';
import styles from './add-wizard.module.css';
import { errorCopy, slugifyLabel } from './providers.js';
import { Stepper } from './SharedSteps.jsx';

// Capability labels for the permission rows. Telegram's single capability
// is read+write; we still render the row for visual parity with the other
// auth flows and to document what's being granted.
const CAP_LABELS = {
    telegram: 'Telegram messages',
};

export function ExplainerStep({ provider, onBack, onNext }) {
    return (
        <>
            <Stepper step={1} />
            <div className={styles.wzBody}>
                <h2 className={styles.wzTitle}>Connect {provider.title}</h2>
                <p className={styles.wzSubtitle}>
                    You'll need a <strong>bot token</strong> from @BotFather and
                    {' '}<strong>your Telegram user ID</strong> from @userinfobot.
                </p>
                <div className={styles.wzContent}>
                    <Callout
                        tone="info"
                        description={
                            'Telegram bots are publicly reachable by anyone who finds '
                            + 'the bot\'s @username. Access is gated by your user-ID '
                            + 'allowlist on the server — no one outside it can drive '
                            + 'the bot.'
                        }
                    />
                    <div className={styles.chipStack}>
                        <span className={styles.chip}>
                            <i className="bi bi-check2" /> Token never leaves the broker process
                        </span>
                        <span className={styles.chip}>
                            <i className="bi bi-check2" /> User-ID allowlist enforced server-side
                        </span>
                        <span className={styles.chip}>
                            <i className="bi bi-check2" /> Revocable from @BotFather at any time
                        </span>
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
    const trimmedToken = form.token.trim();
    const trimmedAllowed = form.allowedUserIds.trim();
    const trimmedName = form.instanceName.trim();
    // user_suffix derives from the instance name. Empty defaults to "personal"
    // — that's the most common single-bot case and removes a required field.
    const effectiveName = trimmedName || 'personal';
    const userSuffix = slugifyLabel(effectiveName);
    const canSubmit = trimmedToken && trimmedAllowed && userSuffix;
    return (
        <>
            <Stepper step={2} />
            <div className={styles.wzBodyLeft}>
                <h2 className={styles.wzTitle}>Paste your bot details</h2>
                <p className={styles.wzSubtitle}>
                    Create a bot with @BotFather (run <code>/newbot</code>) and copy
                    its token. Get your user ID from @userinfobot.
                </p>
                <div className={styles.wzContent}>
                    <a
                        className={styles.linkBtn}
                        href={provider.botFatherUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                    >
                        <span>
                            <i className="bi bi-box-arrow-up-right" /> Open @BotFather
                        </span>
                        <span className={styles.linkBtnHint}>t.me/BotFather</span>
                    </a>
                    <a
                        className={styles.linkBtn}
                        href={provider.userInfoBotUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                    >
                        <span>
                            <i className="bi bi-box-arrow-up-right" /> Open @userinfobot (get your user ID)
                        </span>
                        <span className={styles.linkBtnHint}>t.me/userinfobot</span>
                    </a>

                    <div className={styles.field}>
                        <label className={styles.fieldLabel}>Bot token</label>
                        <input
                            className={`${styles.input} ${styles.inputMono}`}
                            type="password"
                            placeholder="1234567890:ABC-DEF..."
                            value={form.token}
                            onChange={(e) => setForm(f => ({ ...f, token: e.target.value }))}
                            data-testid="wizard-bot-token"
                        />
                        <span className={styles.fieldHint}>
                            Pasted verbatim from BotFather — whitespace is trimmed.
                        </span>
                    </div>

                    <div className={styles.field}>
                        <label className={styles.fieldLabel}>Allowed Telegram user IDs</label>
                        <input
                            className={styles.input}
                            placeholder="123456789, 987654321"
                            value={form.allowedUserIds}
                            onChange={(e) => setForm(f => ({ ...f, allowedUserIds: e.target.value }))}
                            data-testid="wizard-allowed-user-ids"
                        />
                        <span className={styles.fieldHint}>
                            Comma-separated numeric IDs. Only senders on this list can
                            drive the bot — everyone else is silently dropped.
                        </span>
                    </div>

                    <div className={styles.field}>
                        <label className={styles.fieldLabel}>Instance name</label>
                        <input
                            className={styles.input}
                            placeholder="personal"
                            value={form.instanceName}
                            onChange={(e) => setForm(f => ({ ...f, instanceName: e.target.value }))}
                            data-testid="wizard-instance-name"
                        />
                        <span className={styles.fieldHint}>
                            How this Telegram setup is identified. Becomes
                            <code> telegram_{userSuffix || 'personal'}</code> in the
                            integration list. Leave blank for "personal".
                        </span>
                    </div>

                    <div className={styles.subsectionLabel}>Permissions</div>
                    <div className={styles.permStack}>
                        {(provider.capabilities || []).map(cap => (
                            <div key={cap} className={styles.permRow}>
                                <span className={styles.permLabel}>
                                    {CAP_LABELS[cap] || cap}
                                </span>
                                <select
                                    className={styles.accessSelect}
                                    value={form.permissions[cap] || 'rw'}
                                    onChange={(e) => setForm(f => ({
                                        ...f,
                                        permissions: {
                                            ...f.permissions,
                                            [cap]: e.target.value,
                                        },
                                    }))}
                                    data-testid={`wizard-perm-${cap}`}
                                >
                                    <option value="rw">Read + Write</option>
                                    <option value="r">Read only</option>
                                </select>
                            </div>
                        ))}
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
                            <div className={styles.checkLabel}>Authenticating with Telegram</div>
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
