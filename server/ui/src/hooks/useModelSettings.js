import { useState, useEffect } from 'react';

const _SETTINGS_KEY = 'computron_settings';

function _loadSavedSettings() {
    try {
        return JSON.parse(localStorage.getItem(_SETTINGS_KEY) || '{}');
    } catch {
        return {};
    }
}

export default function useModelSettings() {
    const [availableModels, setAvailableModels] = useState([]);
    const [selectedModel, setSelectedModel] = useState('');
    const [contextKb, setContextKb] = useState(() => _loadSavedSettings().contextKb ?? '60');
    const [think, setThink] = useState(() => {
        const s = _loadSavedSettings();
        return 'think' in s ? s.think : true;
    });
    const [persistThinking, setPersistThinking] = useState(() => {
        const s = _loadSavedSettings();
        return 'persistThinking' in s ? s.persistThinking : true;
    });
    const [temperature, setTemperature] = useState(() => _loadSavedSettings().temperature ?? '');
    const [topK, setTopK] = useState(() => _loadSavedSettings().topK ?? '');
    const [topP, setTopP] = useState(() => _loadSavedSettings().topP ?? '');
    const [repeatPenalty, setRepeatPenalty] = useState(() => _loadSavedSettings().repeatPenalty ?? '');
    const [numPredict, setNumPredict] = useState(() => _loadSavedSettings().numPredict ?? '-1');
    const [unlimitedTurns, setUnlimitedTurns] = useState(() => {
        const s = _loadSavedSettings();
        return 'unlimitedTurns' in s ? s.unlimitedTurns : true;
    });
    const [agentTurns, setAgentTurns] = useState(() => _loadSavedSettings().agentTurns ?? '15');

    // Fetch available models on mount
    useEffect(() => {
        fetch('/api/models')
            .then((r) => r.json())
            .then((data) => {
                const models = data.models || [];
                setAvailableModels(models);
                const saved = _loadSavedSettings();
                // Restore saved model even if it's not in the local list
                // (could be a cloud model or one not pulled yet)
                const model = saved.selectedModel
                    ? saved.selectedModel
                    : data.default || '';
                setSelectedModel(model);
            })
            .catch(() => {}); // silently ignore if ollama is unreachable
    }, []);

    // Persist settings to localStorage whenever they change
    useEffect(() => {
        // Skip saving before the model list has loaded (selectedModel is still '')
        if (!selectedModel) return;
        try {
            localStorage.setItem(_SETTINGS_KEY, JSON.stringify({
                selectedModel, contextKb, think, persistThinking, temperature, topK, topP, repeatPenalty,
                numPredict, unlimitedTurns, agentTurns,
            }));
        } catch { /* ignore quota errors */ }
    }, [selectedModel, contextKb, think, persistThinking, temperature, topK, topP, repeatPenalty, numPredict, unlimitedTurns, agentTurns]);

    return {
        availableModels,
        selectedModel, setSelectedModel,
        contextKb, setContextKb,
        think, setThink,
        persistThinking, setPersistThinking,
        temperature, setTemperature,
        topK, setTopK,
        topP, setTopP,
        repeatPenalty, setRepeatPenalty,
        numPredict, setNumPredict,
        unlimitedTurns, setUnlimitedTurns,
        agentTurns, setAgentTurns,
    };
}
