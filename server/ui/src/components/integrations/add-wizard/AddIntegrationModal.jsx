import { useEffect, useState } from 'react';

import styles from './add-wizard.module.css';
import { slugifyEmail } from './providers.js';
import { ProviderPicker, SuccessScreen } from './SharedSteps.jsx';
import { ExplainerStep, CredentialsStep, VerifyingStep } from './AppPasswordSteps.jsx';
import { OauthCapabilitiesStep, OauthGcpSetupStep, OauthRedirectStep } from './OAuthSteps.jsx';

export default function AddIntegrationModal({ onClose, onAdded }) {
    const [provider, setProvider] = useState(null);
    const [step, setStep] = useState(1);
    const [form, setForm] = useState({
        email: '',
        password: '',
        label: '',
        writeAllowed: false,
    });
    const [oauth, setOauth] = useState({
        clientId: '',
        clientSecret: '',
        capabilities: {},
        pending: null,
        status: null,
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

    const handleOauthStart = async () => {
        setSubmitting(true);
        setError(null);
        const scopes = [...(provider.baseScopes || [])];
        for (const group of provider.capabilityGroups) {
            if (oauth.capabilities[group.id]) {
                scopes.push(...group.scopes);
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
                    write_allowed: form.writeAllowed,
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
                    setResult({id: body.integration_id});
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
                            if (p.authFlow === 'oauth_device') {
                                const caps = {};
                                for (const g of p.capabilityGroups) {
                                    caps[g.id] = !!g.defaultChecked;
                                }
                                setOauth({
                                    clientId: '', clientSecret: '',
                                    capabilities: caps, pending: null, status: null,
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
                                email: '', password: '', label: '', writeAllowed: false,
                            });
                            setOauth({
                                clientId: '', clientSecret: '',
                                capabilities: {}, pending: null, status: null,
                            });
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
