import { useEffect, useState } from 'react';

import styles from './add-wizard.module.css';
import { slugifyEmail } from './providers.js';
import { ProviderPicker, SuccessScreen } from './SharedSteps.jsx';
import { ExplainerStep, CredentialsStep, VerifyingStep } from './AppPasswordSteps.jsx';
import { OauthCapabilitiesStep, OauthGcpSetupStep, OauthRedirectStep } from './OAuthSteps.jsx';
import {
    IcloudDriveExplainerStep,
    IcloudDriveCredentialsStep,
    IcloudDriveTwoFactorStep,
} from './IcloudDriveSteps.jsx';

const TWO_FACTOR_INITIAL = { sessionId: null, code: '' };

export default function AddIntegrationModal({ onClose, onAdded }) {
    const [provider, setProvider] = useState(null);
    const [step, setStep] = useState(1);
    const [form, setForm] = useState({
        email: '',
        password: '',
        label: '',
        permissions: {},
    });
    const [oauth, setOauth] = useState({
        clientId: '',
        clientSecret: '',
        capabilities: {},
        access: {},
        pending: null,
        status: null,
    });
    const [twoFactor, setTwoFactor] = useState(TWO_FACTOR_INITIAL);
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
                    permissions: Object.fromEntries(
                        (provider.capabilities || []).map(
                            cap => [cap, form.permissions[cap] || 'r'],
                        ),
                    ),
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

    // iCloud Drive: step 2 → POST credentials, which makes Apple push a 2FA
    // code; on success advance to the code-entry step.
    const handleIcloudPreauthStart = async () => {
        setSubmitting(true);
        setError(null);
        const email = form.email.trim();
        try {
            const resp = await fetch('/api/integrations/icloud-drive/preauth', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password: form.password }),
            });
            const body = await resp.json().catch(() => ({}));
            if (!resp.ok || !body?.session_id) {
                setError({
                    code: body?.error?.code || 'ERROR',
                    message: body?.error?.message || `HTTP ${resp.status}`,
                });
                setSubmitting(false);
                return;
            }
            setTwoFactor({ sessionId: body.session_id, code: '' });
            setStep(3);
            setSubmitting(false);
        } catch (err) {
            setError({ code: 'NETWORK', message: err?.message || 'Request failed' });
            setSubmitting(false);
        }
    };

    // iCloud Drive: step 3 → verify the 2FA code (yields a trust token), then
    // run the normal add with {email, password, trust_token} in the auth blob.
    const handleIcloudVerifyAndAdd = async () => {
        setSubmitting(true);
        setError(null);
        const email = form.email.trim();
        const label = form.label.trim() || `${provider.title} · ${email}`;
        try {
            const verifyResp = await fetch('/api/integrations/icloud-drive/preauth/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: twoFactor.sessionId, code: twoFactor.code.trim() }),
            });
            const verifyBody = await verifyResp.json().catch(() => ({}));
            if (!verifyResp.ok || !verifyBody?.trust_token) {
                setError({
                    code: verifyBody?.error?.code || 'ERROR',
                    message: verifyBody?.error?.message || `HTTP ${verifyResp.status}`,
                });
                setSubmitting(false);
                return;
            }
            const addResp = await fetch('/api/integrations', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    slug: provider.slug,
                    label,
                    auth_blob: {
                        email,
                        password: form.password,
                        trust_token: verifyBody.trust_token,
                    },
                    permissions: { drive: form.permissions.drive || 'r' },
                }),
            });
            const addBody = await addResp.json().catch(() => ({}));
            if (!addResp.ok) {
                setError({
                    code: addBody?.error?.code || 'ERROR',
                    message: addBody?.error?.message || `HTTP ${addResp.status}`,
                });
                setSubmitting(false);
                return;
            }
            setResult(addBody);
            setSubmitting(false);
        } catch (err) {
            setError({ code: 'NETWORK', message: err?.message || 'Request failed' });
            setSubmitting(false);
        }
    };

    const handleOauthStart = async () => {
        setSubmitting(true);
        setError(null);
        const scopes = [...(provider.baseScopes || [])];
        const permissions = {};
        for (const group of provider.capabilityGroups) {
            if (oauth.capabilities[group.id]) {
                scopes.push(...group.readScopes);
                const access = oauth.access[group.id] || 'r';
                if (access === 'rw' && group.writeScopes?.length) {
                    scopes.push(...group.writeScopes);
                }
                permissions[group.id] = access;
            }
        }
        const email = form.email.trim();
        const label = form.label.trim() || `${provider.title} · ${email}`;
        const userSuffix = slugifyEmail(email);
        if (!userSuffix) {
            setError({code: 'BAD_REQUEST', message: 'Account email is required'});
            setSubmitting(false);
            return;
        }
        try {
            const resp = await fetch('/api/integrations/oauth/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    slug: provider.slug,
                    user_suffix: userSuffix,
                    label,
                    client_id: oauth.clientId.trim(),
                    client_secret: oauth.clientSecret.trim(),
                    scopes,
                    permissions,
                }),
            });
            const body = await resp.json().catch(() => ({}));
            if (!resp.ok) {
                setError({
                    code: body?.error?.code || 'ERROR',
                    message: body?.error?.message || `HTTP ${resp.status}`,
                });
                setSubmitting(false);
                return;
            }
            // window.open from inside an event handler dodges popup blockers.
            const popup = window.open(
                body.authorize_url,
                'computron-google-oauth',
                'width=600,height=720',
            );
            setOauth(o => ({...o, pending: body, status: 'pending', popup}));
            setStep(3);
            setSubmitting(false);
        } catch (err) {
            setError({code: 'NETWORK', message: err?.message || 'Request failed'});
            setSubmitting(false);
        }
    };

    useEffect(() => {
        if (provider?.authFlow !== 'oauth_device') return undefined;
        if (!oauth.pending || oauth.status !== 'pending') return undefined;
        let cancelled = false;
        const tick = async () => {
            try {
                const resp = await fetch(
                    `/api/integrations/oauth/status/${encodeURIComponent(oauth.pending.state)}`,
                );
                const body = await resp.json().catch(() => ({}));
                if (cancelled) return;
                if (!resp.ok) {
                    setOauth(o => ({...o, status: 'error'}));
                    setError({
                        code: body?.error?.code || 'ERROR',
                        message: body?.error?.message || `HTTP ${resp.status}`,
                    });
                    return;
                }
                if (body.status === 'success') {
                    setOauth(o => ({...o, status: 'success'}));
                    const perms = {};
                    for (const group of provider.capabilityGroups || []) {
                        if (oauth.capabilities[group.id]) {
                            perms[group.id] = oauth.access[group.id] || 'r';
                        }
                    }
                    setResult({id: body.integration_id, permissions: perms});
                    return;
                }
                if (body.status === 'denied' || body.status === 'expired'
                    || body.status === 'error') {
                    setOauth(o => ({...o, status: body.status}));
                    if (body.error) setError(body.error);
                    return;
                }
            } catch (err) {
                if (cancelled) return;
            }
        };
        const handle = setInterval(tick, 2000);
        return () => { cancelled = true; clearInterval(handle); };
    }, [provider, oauth.pending, oauth.status]);

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
                            setTwoFactor(TWO_FACTOR_INITIAL);
                            if (p.authFlow === 'oauth_device') {
                                const caps = {};
                                const access = {};
                                for (const g of p.capabilityGroups) {
                                    caps[g.id] = true;
                                    access[g.id] = g.defaultAccess || 'r';
                                }
                                setOauth({
                                    clientId: '', clientSecret: '',
                                    capabilities: caps, access,
                                    pending: null, status: null,
                                });
                            }
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
                                email: '', password: '', label: '', permissions: {},
                            });
                            setOauth({
                                clientId: '', clientSecret: '',
                                capabilities: {}, access: {},
                                pending: null, status: null,
                            });
                            setTwoFactor(TWO_FACTOR_INITIAL);
                            setError(null);
                        }}
                        onDone={() => { onAdded?.(); }}
                    />
                ) : provider.authFlow === 'oauth_device' ? (
                    step === 1 ? (
                        <OauthCapabilitiesStep
                            provider={provider}
                            oauth={oauth}
                            setOauth={setOauth}
                            form={form}
                            setForm={setForm}
                            onBack={() => setProvider(null)}
                            onNext={() => setStep(2)}
                        />
                    ) : step === 2 ? (
                        <OauthGcpSetupStep
                            provider={provider}
                            oauth={oauth}
                            setOauth={setOauth}
                            error={error}
                            submitting={submitting}
                            onBack={() => setStep(1)}
                            onCancel={onClose}
                            onSubmit={handleOauthStart}
                        />
                    ) : (
                        <OauthRedirectStep
                            provider={provider}
                            oauth={oauth}
                            error={error}
                            onCancel={onClose}
                            onRestart={() => {
                                setOauth(o => ({
                                    ...o, pending: null, status: null,
                                }));
                                setError(null);
                                setStep(2);
                            }}
                        />
                    )
                ) : provider.authFlow === 'app_password_2fa' ? (
                    step === 1 ? (
                        <IcloudDriveExplainerStep
                            provider={provider}
                            onBack={() => setProvider(null)}
                            onNext={() => setStep(2)}
                        />
                    ) : step === 2 ? (
                        <IcloudDriveCredentialsStep
                            provider={provider}
                            form={form}
                            setForm={setForm}
                            error={error}
                            submitting={submitting}
                            onBack={() => { setStep(1); setError(null); }}
                            onCancel={onClose}
                            onSubmit={handleIcloudPreauthStart}
                        />
                    ) : (
                        <IcloudDriveTwoFactorStep
                            provider={provider}
                            form={form}
                            twoFactor={twoFactor}
                            setTwoFactor={setTwoFactor}
                            error={error}
                            submitting={submitting}
                            onBack={() => { setStep(2); setError(null); }}
                            onCancel={onClose}
                            onSubmit={handleIcloudVerifyAndAdd}
                        />
                    )
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
