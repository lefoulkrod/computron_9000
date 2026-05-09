export const INFERENCE_FIELDS = [
    'temperature', 'top_k', 'top_p', 'repeat_penalty',
    'think', 'reasoning_effort', 'reasoning_summary', 'thinking_budget',
];

export const FIELD_SUPPORT = {
    temperature:      ['ollama', 'openai', 'anthropic', 'openai_compat', 'openrouter'],
    top_k:            ['ollama', 'anthropic'],
    top_p:            ['ollama', 'openai', 'anthropic', 'openai_compat', 'openrouter'],
    repeat_penalty:   ['ollama'],
    num_ctx:          ['ollama'],
    num_predict:      ['ollama', 'openai', 'anthropic', 'openai_compat', 'openrouter'],
    max_iterations:   ['ollama', 'openai', 'anthropic', 'openai_compat', 'openrouter'],
    think:            ['ollama', 'openai', 'anthropic', 'openrouter'],
    reasoning_effort: ['openai'],
    reasoning_summary: ['openai'],
    thinking_budget:  ['anthropic'],
};

export const THINKING_DEFAULTS = {
    reasoning_effort: 'medium',
    reasoning_summary: 'auto',
    thinking_budget: 'standard',
};

export function isSupported(field, provider) {
    const providers = FIELD_SUPPORT[field];
    return !providers || providers.includes(provider);
}
