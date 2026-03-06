import { useState, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import styles from './CustomToolsPanel.module.css';
import localStyles from './ModelSettingsPanel.module.css';

const SETTING_TIPS = {
    model: 'Select the model to use for inference',
    context: 'Max context window in K tokens — use more for long docs, less to save memory',
    think: 'Let the model reason step-by-step before answering — good for math, logic, coding',
    thinkHistory: 'Store thinking in conversation history — disable for models that get confused by their own reasoning',
    temp: '0.0 = precise code/facts, 0.5 = general chat, 1.0+ = brainstorming/stories',
    topK: '10 = factual Q&A, 40 = general use, 100+ = creative writing',
    topP: '0.5 = stick to likely words, 0.9 = general use, 1.0 = max variety',
    repPen: '1.0 = off, 1.1 = general use, 1.5+ = stop looping in long outputs',
    numPredict: '-1 = unlimited, 4096 = short replies, 16384+ = long code generation',
    turns: 'How many tool calls the agent can chain per message',
};

function InfoTip({ text }) {
    const iconRef = useRef(null);
    const [pos, setPos] = useState(null);

    const show = useCallback(() => {
        const el = iconRef.current;
        if (!el) return;
        const rect = el.getBoundingClientRect();
        setPos({ left: rect.right + 8, top: rect.top + rect.height / 2 });
    }, []);

    const hide = useCallback(() => setPos(null), []);

    return (
        <span className={localStyles.infoWrap} onMouseEnter={show} onMouseLeave={hide}>
            <svg ref={iconRef} className={localStyles.infoIcon} viewBox="0 0 16 16" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
                <path d="M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM7.25 5a.75.75 0 1 1 1.5 0 .75.75 0 0 1-1.5 0ZM7.25 7.25a.75.75 0 0 1 1.5 0v3.5a.75.75 0 0 1-1.5 0v-3.5Z" />
            </svg>
            {pos && createPortal(
                <span
                    className={localStyles.tooltip}
                    style={{ left: pos.left, top: pos.top, transform: 'translateY(-50%)' }}
                >{text}</span>,
                document.body,
            )}
        </span>
    );
}

export default function ModelSettingsPanel({
    models, selectedModel, onModelChange,
    contextKb, onContextKbChange,
    think, onThinkChange,
    persistThinking, onPersistThinkingChange,
    temperature, onTemperatureChange,
    topK, onTopKChange,
    topP, onTopPChange,
    repeatPenalty, onRepeatPenaltyChange,
    numPredict, onNumPredictChange,
    unlimitedTurns, onUnlimitedTurnsChange,
    agentTurns, onAgentTurnsChange,
    disabled,
}) {
    const [collapsed, setCollapsed] = useState(true);

    return (
        <div className={styles.panel}>
            <div className={styles.header} onClick={() => setCollapsed((c) => !c)}>
                <span className={styles.title}>Settings</span>
                <span className={styles.chevron}>{collapsed ? '▶' : '▼'}</span>
            </div>
            {!collapsed && (
                <div className={localStyles.body}>
                    <label className={localStyles.row}>
                        <span className={localStyles.label}>Model<InfoTip text={SETTING_TIPS.model} /></span>
                        <select
                            className={localStyles.select}
                            value={selectedModel}
                            onChange={(e) => onModelChange(e.target.value)}
                            disabled={disabled}
                            aria-label="Model name"
                        >
                            {(models || []).map((m) => (
                                <option key={m} value={m}>{m}</option>
                            ))}
                        </select>
                    </label>
                    <label className={localStyles.row}>
                        <span className={localStyles.label}>Context<InfoTip text={SETTING_TIPS.context} /></span>
                        <div className={localStyles.inputGroup}>
                            <input
                                type="number"
                                className={localStyles.numInput}
                                value={contextKb}
                                onChange={(e) => onContextKbChange(e.target.value)}
                                min={1}
                                placeholder="auto"
                                disabled={disabled}
                                aria-label="Context size in K tokens"
                            />
                            <span className={localStyles.unit}>K tok</span>
                        </div>
                    </label>
                    <div className={localStyles.row}>
                        <span className={localStyles.label}>Think<InfoTip text={SETTING_TIPS.think} /></span>
                        <label className={localStyles.toggleLabel}>
                            <input
                                type="checkbox"
                                className={localStyles.toggleInput}
                                checked={think}
                                onChange={(e) => onThinkChange(e.target.checked)}
                                disabled={disabled}
                            />
                            <span className={localStyles.toggle} />
                        </label>
                    </div>
                    <div className={localStyles.row}>
                        <span className={localStyles.label}>Think history<InfoTip text={SETTING_TIPS.thinkHistory} /></span>
                        <label className={localStyles.toggleLabel}>
                            <input
                                type="checkbox"
                                className={localStyles.toggleInput}
                                checked={persistThinking}
                                onChange={(e) => onPersistThinkingChange(e.target.checked)}
                                disabled={disabled}
                            />
                            <span className={localStyles.toggle} />
                        </label>
                    </div>
                    <label className={localStyles.row}>
                        <span className={localStyles.label}>Temp<InfoTip text={SETTING_TIPS.temp} /></span>
                        <input
                            type="number"
                            className={localStyles.numInput}
                            value={temperature}
                            onChange={(e) => onTemperatureChange(e.target.value)}
                            min={0} max={2} step={0.1}
                            placeholder="auto"
                            disabled={disabled}
                            aria-label="Temperature"
                        />
                    </label>
                    <label className={localStyles.row}>
                        <span className={localStyles.label}>Top K<InfoTip text={SETTING_TIPS.topK} /></span>
                        <input
                            type="number"
                            className={localStyles.numInput}
                            value={topK}
                            onChange={(e) => onTopKChange(e.target.value)}
                            min={0} step={1}
                            placeholder="auto"
                            disabled={disabled}
                            aria-label="Top K"
                        />
                    </label>
                    <label className={localStyles.row}>
                        <span className={localStyles.label}>Top P<InfoTip text={SETTING_TIPS.topP} /></span>
                        <input
                            type="number"
                            className={localStyles.numInput}
                            value={topP}
                            onChange={(e) => onTopPChange(e.target.value)}
                            min={0} max={1} step={0.05}
                            placeholder="auto"
                            disabled={disabled}
                            aria-label="Top P"
                        />
                    </label>
                    <label className={localStyles.row}>
                        <span className={localStyles.label}>Rep pen<InfoTip text={SETTING_TIPS.repPen} /></span>
                        <input
                            type="number"
                            className={localStyles.numInput}
                            value={repeatPenalty}
                            onChange={(e) => onRepeatPenaltyChange(e.target.value)}
                            min={0} step={0.05}
                            placeholder="auto"
                            disabled={disabled}
                            aria-label="Repeat penalty"
                        />
                    </label>
                    <label className={localStyles.row}>
                        <span className={localStyles.label}>Max output<InfoTip text={SETTING_TIPS.numPredict} /></span>
                        <div className={localStyles.inputGroup}>
                            <input
                                type="number"
                                className={localStyles.numInput}
                                value={numPredict}
                                onChange={(e) => onNumPredictChange(e.target.value)}
                                min={-1} step={1}
                                placeholder="unlimited"
                                disabled={disabled}
                                aria-label="Max output tokens"
                            />
                            <span className={localStyles.unit}>tok</span>
                        </div>
                    </label>
                    <div className={localStyles.row}>
                        <span className={localStyles.label}>Turns<InfoTip text={SETTING_TIPS.turns} /></span>
                        <div className={localStyles.turnsGroup}>
                            <label className={localStyles.toggleLabel}>
                                <input
                                    type="checkbox"
                                    className={localStyles.toggleInput}
                                    checked={unlimitedTurns}
                                    onChange={(e) => onUnlimitedTurnsChange(e.target.checked)}
                                    disabled={disabled}
                                />
                                <span className={localStyles.toggle} />
                            </label>
                            {unlimitedTurns
                                ? <span className={localStyles.turnsHint}>unlimited</span>
                                : <input
                                    type="number"
                                    className={localStyles.numInput}
                                    value={agentTurns}
                                    onChange={(e) => onAgentTurnsChange(e.target.value)}
                                    min={1} step={1}
                                    placeholder="15"
                                    disabled={disabled}
                                    aria-label="Agent turn limit"
                                />
                            }
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
