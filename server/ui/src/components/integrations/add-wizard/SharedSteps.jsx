import styles from './add-wizard.module.css';
import { PROVIDERS } from './providers.js';

export function ProviderPicker({ onPick, onCancel }) {
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
                <button className={styles.btnGhost} onClick={onCancel}>Cancel</button>
            </div>
        </>
    );
}

export function Stepper({ step }) {
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

export function SuccessScreen({ provider, form, result, onAddAnother, onDone }) {
    return (
        <>
            <Stepper step={4} />
            <div className={styles.wzBodyLeft}>
                <h2 className={styles.wzTitle}>{provider.title} connected</h2>
                <p className={styles.wzSubtitle}>
                    Your agent can now read your email.
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
                        </tbody>
                    </table>
                </div>
            </div>
            <div className={styles.footer}>
                <div className={styles.footerRight}>
                    <button className={styles.btnOutline} onClick={onAddAnother}>
                        <i className="bi bi-plus-lg" /> Add another
                    </button>
                    <button
                        className={styles.btnFilled}
                        onClick={onDone}
                        data-testid="wizard-done"
                    >
                        Done
                    </button>
                </div>
            </div>
        </>
    );
}
