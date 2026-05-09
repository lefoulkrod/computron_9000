import styles from './inference.module.css';
import { INFERENCE_FIELDS, THINKING_DEFAULTS, isSupported } from './inferenceConstants.js';

const PRESETS = {
    balanced: {
        _default: { temperature: 0.7 },
    },
    creative: {
        _default: { temperature: 1.0, top_p: 0.95 },
    },
    precise: {
        _default: { temperature: 0.2, top_k: 40 },
    },
    code: {
        _default:      { temperature: 0.3, think: true },
        anthropic:     { temperature: 1.0, think: true, thinking_budget: 'standard' },
        openai_compat: { temperature: 0.3 },
    },
};

const STATIC_HINTS = {
    balanced: '0.7 temp',
    creative: '1.0 temp, 0.95 top_p',
    precise: '0.2 temp, 40 top_k',
};

function getPresetHint(presetId, provider) {
    if (presetId === 'code') {
        if (provider === 'anthropic') return '1.0 temp, think';
        if (provider === 'openai_compat') return '0.3 temp';
        return '0.3 temp, think';
    }
    return STATIC_HINTS[presetId] || '';
}

const PRESET_IDS = ['balanced', 'creative', 'precise', 'code'];
const PRESET_LABELS = { balanced: 'Balanced', creative: 'Creative', precise: 'Precise', code: 'Code' };

export function resolvePreset(presetId, provider) {
    const entry = PRESETS[presetId];
    if (!entry) return null;
    return entry[provider] || entry._default;
}

export function detectPreset(draft, provider) {
    for (const id of PRESET_IDS) {
        const fields = resolvePreset(id, provider);
        const presetKeys = Object.keys(fields).filter((k) => isSupported(k, provider));
        const allMatch = presetKeys.every((k) => {
            let draftVal = draft[k];
            const presetVal = fields[k];
            // Null thinking fields equal their default for comparison
            if ((draftVal == null || draftVal === '') && k in THINKING_DEFAULTS) {
                draftVal = THINKING_DEFAULTS[k];
            }
            if (typeof presetVal === 'boolean') return draftVal === presetVal;
            if (typeof presetVal === 'string') return draftVal === presetVal;
            return Number(draftVal) === presetVal;
        });
        if (!allMatch) continue;

        const otherKeys = INFERENCE_FIELDS
            .filter((k) => isSupported(k, provider))
            .filter((k) => !presetKeys.includes(k));
        const othersNull = otherKeys.every((k) => {
            const val = draft[k];
            if (val == null || val === '') return true;
            if (k in THINKING_DEFAULTS) return val === THINKING_DEFAULTS[k];
            return false;
        });
        if (othersNull) return id;
    }
    return null;
}

export default function InferencePresets({ provider, activePreset, onApply }) {
    return (
        <div className={styles.presetGrid}>
            {PRESET_IDS.map((id) => (
                <button
                    key={id}
                    className={`${styles.presetBtn} ${activePreset === id ? styles.presetActive : ''}`}
                    onClick={() => onApply(id)}
                >
                    <span className={styles.presetLabel}>{PRESET_LABELS[id]}</span>
                    <span className={styles.presetHint}>{getPresetHint(id, provider)}</span>
                </button>
            ))}
        </div>
    );
}
