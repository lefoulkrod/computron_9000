import { useState } from 'react';
import styles from './inference.module.css';
import ChevronRightIcon from '../icons/ChevronRightIcon';
import ToggleSwitch from '../ToggleSwitch.jsx';
import { isSupported } from './inferenceConstants.js';

const ADVANCED_HELP = {
    temperature: '0.0 = deterministic, 0.7 = general, 1.0+ = creative',
    top_k: '10 = factual, 40 = general, 100+ = creative',
    top_p: '0.5 = focused, 0.9 = general, 1.0 = everything',
    repeat_penalty: '1.0 = off, 1.1 = general, 1.5+ = strongly discourages repetition',
    context: 'Context window in tokens. Higher = more memory, slower',
    max_output: 'Max tokens per response. Leave empty for unlimited (required by Anthropic)',
    iterations: 'Tool-call rounds per turn. Leave empty for unlimited',
    compaction: 'How full the context window gets before old messages are summarized',
    thinking: 'Step-by-step reasoning before answering. Good for math, logic, code',
    reasoning_effort: 'Low = faster/cheaper, medium = balanced, high = thorough reasoning',
    reasoning_summary: 'How much of the model\'s reasoning to show. Auto lets the model decide',
    thinking_budget: 'How many tokens the model can use for reasoning before answering',
};

export default function InferenceAdvanced({ draft, provider, onChange }) {
    const [showAdvanced, setShowAdvanced] = useState(false);

    return (
        <>
            <button
                className={styles.advancedToggle}
                onClick={() => setShowAdvanced((v) => !v)}
            >
                <ChevronRightIcon className={`${styles.chevron} ${showAdvanced ? styles.chevronOpen : ''}`} />
                Advanced Settings
            </button>

            {showAdvanced && (
                <div className={styles.advancedBody}>
                    <div className={styles.advancedField}>
                        <label className={styles.fieldRow}>
                            <span className={styles.fieldLabel}>Temperature</span>
                            <input className={styles.numInput} type="number" data-testid="field-temperature" value={draft.temperature ?? ''} onChange={(e) => onChange('temperature', e.target.value === '' ? null : Number(e.target.value))} min={0} max={2} step={0.1} placeholder="auto" />
                        </label>
                        <span className={styles.fieldHint}>{ADVANCED_HELP.temperature}</span>
                    </div>
                    {isSupported('top_k', provider) && (
                        <div className={styles.advancedField}>
                            <label className={styles.fieldRow}>
                                <span className={styles.fieldLabel}>Top K</span>
                                <input className={styles.numInput} type="number" data-testid="field-top_k" value={draft.top_k ?? ''} onChange={(e) => onChange('top_k', e.target.value === '' ? null : Number(e.target.value))} min={0} step={1} placeholder="auto" />
                            </label>
                            <span className={styles.fieldHint}>{ADVANCED_HELP.top_k}</span>
                        </div>
                    )}
                    <div className={styles.advancedField}>
                        <label className={styles.fieldRow}>
                            <span className={styles.fieldLabel}>Top P</span>
                            <input className={styles.numInput} type="number" data-testid="field-top_p" value={draft.top_p ?? ''} onChange={(e) => onChange('top_p', e.target.value === '' ? null : Number(e.target.value))} min={0} max={1} step={0.05} placeholder="auto" />
                        </label>
                        <span className={styles.fieldHint}>{ADVANCED_HELP.top_p}</span>
                    </div>
                    {isSupported('repeat_penalty', provider) && (
                        <div className={styles.advancedField}>
                            <label className={styles.fieldRow}>
                                <span className={styles.fieldLabel}>Repeat Penalty</span>
                                <input className={styles.numInput} type="number" data-testid="field-repeat_penalty" value={draft.repeat_penalty ?? ''} onChange={(e) => onChange('repeat_penalty', e.target.value === '' ? null : Number(e.target.value))} min={0} step={0.05} placeholder="auto" />
                            </label>
                            <span className={styles.fieldHint}>{ADVANCED_HELP.repeat_penalty}</span>
                        </div>
                    )}
                    {isSupported('context_window', provider) && (
                        <div className={styles.advancedField}>
                            <label className={styles.fieldRow}>
                                <span className={styles.fieldLabel}>Context Window</span>
                                <input className={styles.numInput} type="number" data-testid="field-context_window" value={draft.context_window ?? ''} onChange={(e) => onChange('context_window', e.target.value === '' ? null : Number(e.target.value))} min={1} placeholder="auto" />
                            </label>
                            <span className={styles.fieldHint}>{ADVANCED_HELP.context}</span>
                        </div>
                    )}
                    <div className={styles.advancedField}>
                        <label className={styles.fieldRow}>
                            <span className={styles.fieldLabel}>Max Output</span>
                            <input className={styles.numInput} type="number" data-testid="field-num_predict" value={draft.num_predict ?? ''} onChange={(e) => onChange('num_predict', e.target.value === '' ? null : Number(e.target.value))} min={-1} step={1} placeholder={provider === 'anthropic' ? '16384' : 'unlimited'} />
                        </label>
                        <span className={styles.fieldHint}>{ADVANCED_HELP.max_output}</span>
                    </div>
                    <div className={styles.advancedField}>
                        <label className={styles.fieldRow}>
                            <span className={styles.fieldLabel}>Iterations</span>
                            <input className={styles.numInput} type="number" data-testid="field-max_iterations" value={draft.max_iterations ?? ''} onChange={(e) => onChange('max_iterations', e.target.value === '' ? null : Number(e.target.value))} min={1} step={1} placeholder="unlimited" />
                        </label>
                        <span className={styles.fieldHint}>{ADVANCED_HELP.iterations}</span>
                    </div>
                    {isSupported('compaction_threshold', provider) && (
                        <div className={styles.advancedField} data-testid="field-compaction_threshold">
                            <label className={styles.fieldRow}>
                                <span className={styles.fieldLabel}>Compaction</span>
                                <select
                                    className={styles.selectInput}
                                    value={draft.compaction_threshold ?? 0.75}
                                    onChange={(e) => onChange('compaction_threshold', e.target.value === '0.75' ? null : Number(e.target.value))}
                                    data-testid="compaction-threshold-select"
                                >
                                    <option value={0.5}>50% — Aggressive</option>
                                    <option value={0.65}>65% — Early</option>
                                    <option value={0.75}>75% — Standard</option>
                                    <option value={0.85}>85% — Late</option>
                                    <option value={0.9}>90% — Maximum</option>
                                </select>
                            </label>
                            <span className={styles.fieldHint}>{ADVANCED_HELP.compaction}</span>
                        </div>
                    )}
                    {isSupported('think', provider) && (
                        <div className={styles.advancedField} data-testid="field-think">
                            <label className={styles.fieldRow}>
                                <span className={styles.fieldLabel}>Thinking</span>
                                <ToggleSwitch
                                    checked={draft.think || false}
                                    onChange={(e) => onChange('think', e.target.checked || null)}
                                />
                            </label>
                            <span className={styles.fieldHint}>{ADVANCED_HELP.thinking}</span>
                        </div>
                    )}
                    {draft.think && isSupported('reasoning_effort', provider) && (
                        <div className={styles.advancedField} data-testid="field-reasoning_effort">
                            <label className={styles.fieldRow}>
                                <span className={styles.fieldLabel}>Reasoning Effort</span>
                                <select
                                    className={styles.selectInput}
                                    value={draft.reasoning_effort || 'medium'}
                                    onChange={(e) => onChange('reasoning_effort', e.target.value === 'medium' ? null : e.target.value)}
                                    data-testid="reasoning-effort-select"
                                >
                                    <option value="low">Low</option>
                                    <option value="medium">Medium</option>
                                    <option value="high">High</option>
                                </select>
                            </label>
                            <span className={styles.fieldHint}>{ADVANCED_HELP.reasoning_effort}</span>
                        </div>
                    )}
                    {draft.think && isSupported('reasoning_summary', provider) && (
                        <div className={styles.advancedField} data-testid="field-reasoning_summary">
                            <label className={styles.fieldRow}>
                                <span className={styles.fieldLabel}>Reasoning Summary</span>
                                <select
                                    className={styles.selectInput}
                                    value={draft.reasoning_summary || 'auto'}
                                    onChange={(e) => onChange('reasoning_summary', e.target.value === 'auto' ? null : e.target.value)}
                                    data-testid="reasoning-summary-select"
                                >
                                    <option value="auto">Auto</option>
                                    <option value="concise">Concise</option>
                                    <option value="detailed">Detailed</option>
                                </select>
                            </label>
                            <span className={styles.fieldHint}>{ADVANCED_HELP.reasoning_summary}</span>
                        </div>
                    )}
                    {draft.think && isSupported('thinking_budget', provider) && (
                        <div className={styles.advancedField} data-testid="field-thinking_budget">
                            <label className={styles.fieldRow}>
                                <span className={styles.fieldLabel}>Thinking Budget</span>
                                <select
                                    className={styles.selectInput}
                                    value={draft.thinking_budget || 'standard'}
                                    onChange={(e) => onChange('thinking_budget', e.target.value === 'standard' ? null : e.target.value)}
                                    data-testid="thinking-budget-select"
                                >
                                    <option value="minimal">Minimal (1,024 tokens)</option>
                                    <option value="standard">Standard ({Math.max(1024, Math.floor((draft.num_predict || 16384) / 2)).toLocaleString()} tokens)</option>
                                    <option value="extended">Extended ({(draft.num_predict || 16384).toLocaleString()} tokens)</option>
                                </select>
                            </label>
                            <span className={styles.fieldHint}>{ADVANCED_HELP.thinking_budget}</span>
                        </div>
                    )}
                </div>
            )}
        </>
    );
}
