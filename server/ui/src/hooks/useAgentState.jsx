import { createContext, useContext, useReducer } from 'react';
import { mergeTerminalEvent } from '../utils/agentUtils.js';

/**
 * Initial state for the agent tree.
 */
const _INITIAL_STATE = {
    agents: {},
    rootId: null,
    selectedAgentId: null,
};

/**
 * Create a fresh agent node.
 */
function _makeAgent(id, name, parentId, instruction, startedAt) {
    return {
        id,
        name,
        parentId,
        status: 'running',
        childIds: [],
        startedAt,
        instruction: instruction || '',
        activityLog: [],
        browserSnapshot: null,
        terminalLines: [],
        desktopActive: false,
        generationPreview: null,
        activeTool: null,
        iteration: null,
        maxIterations: null,
        contextUsage: null,
    };
}

/**
 * Reducer for agent tree state.
 */
function _agentReducer(state, action) {
    switch (action.type) {
        case 'AGENT_STARTED': {
            const { agentId, agentName, parentAgentId, instruction, timestamp } = action;
            const agent = _makeAgent(agentId, agentName, parentAgentId, instruction, timestamp);
            const agents = { ...state.agents, [agentId]: agent };

            // Link parent → child
            if (parentAgentId && agents[parentAgentId]) {
                agents[parentAgentId] = {
                    ...agents[parentAgentId],
                    childIds: [...agents[parentAgentId].childIds, agentId],
                };
            }

            return {
                ...state,
                agents,
                rootId: state.rootId || (parentAgentId ? state.rootId : agentId),
            };
        }

        case 'AGENT_COMPLETED': {
            const { agentId, status } = action;
            const agent = state.agents[agentId];
            if (!agent) return state;
            return {
                ...state,
                agents: {
                    ...state.agents,
                    [agentId]: { ...agent, status, activeTool: null },
                },
            };
        }

        case 'APPEND_STREAM_CHUNK': {
            // Merge content and thinking into their respective last entries
            // in a single state update. This avoids interleaving fragments.
            const { agentId, content, thinking } = action;
            const agent = state.agents[agentId];
            if (!agent) return state;
            let log = [...agent.activityLog];

            const mergeOrAppend = (type, key, text) => {
                if (!text) return;
                const lastIdx = log.length - 1;
                if (lastIdx >= 0 && log[lastIdx].type === type) {
                    log[lastIdx] = { ...log[lastIdx], [key]: (log[lastIdx][key] || '') + text };
                } else {
                    log.push({ type, [key]: text, timestamp: Date.now() });
                }
            };

            // Thinking first, then content — matches the model's output order
            mergeOrAppend('thinking', 'thinking', thinking);
            mergeOrAppend('content', 'content', content);

            return {
                ...state,
                agents: {
                    ...state.agents,
                    [agentId]: { ...agent, activityLog: log },
                },
            };
        }

        case 'APPEND_ACTIVITY': {
            const { agentId, entry } = action;
            const agent = state.agents[agentId];
            if (!agent) return state;
            const log = agent.activityLog;
            const last = log.length > 0 ? log[log.length - 1] : null;

            // Merge consecutive content or thinking tokens into one entry
            if (last && last.type === entry.type && (entry.type === 'content' || entry.type === 'thinking')) {
                const key = entry.type === 'content' ? 'content' : 'thinking';
                const merged = { ...last, [key]: (last[key] || '') + (entry[key] || '') };
                const newLog = [...log.slice(0, -1), merged];
                return {
                    ...state,
                    agents: {
                        ...state.agents,
                        [agentId]: { ...agent, activityLog: newLog },
                    },
                };
            }

            return {
                ...state,
                agents: {
                    ...state.agents,
                    [agentId]: {
                        ...agent,
                        activityLog: [...log, entry],
                    },
                },
            };
        }

        case 'UPDATE_BROWSER_SNAPSHOT': {
            const { agentId, snapshot } = action;
            const agent = state.agents[agentId];
            if (!agent) return state;
            return {
                ...state,
                agents: {
                    ...state.agents,
                    [agentId]: { ...agent, browserSnapshot: snapshot },
                },
            };
        }

        case 'UPDATE_TERMINAL': {
            const { agentId, event } = action;
            const agent = state.agents[agentId];
            if (!agent) return state;
            return {
                ...state,
                agents: {
                    ...state.agents,
                    [agentId]: { ...agent, terminalLines: mergeTerminalEvent(agent.terminalLines, event) },
                },
            };
        }

        case 'UPDATE_DESKTOP_ACTIVE': {
            const { agentId } = action;
            const agent = state.agents[agentId];
            if (!agent) return state;
            return {
                ...state,
                agents: {
                    ...state.agents,
                    [agentId]: { ...agent, desktopActive: true },
                },
            };
        }

        case 'UPDATE_GENERATION_PREVIEW': {
            const { agentId, preview } = action;
            const agent = state.agents[agentId];
            if (!agent) return state;
            return {
                ...state,
                agents: {
                    ...state.agents,
                    [agentId]: { ...agent, generationPreview: preview },
                },
            };
        }

        case 'UPDATE_ACTIVE_TOOL': {
            const { agentId, toolName } = action;
            const agent = state.agents[agentId];
            if (!agent) return state;
            return {
                ...state,
                agents: {
                    ...state.agents,
                    [agentId]: { ...agent, activeTool: toolName },
                },
            };
        }

        case 'UPDATE_ITERATION': {
            const { agentId, iteration, maxIterations, contextUsage } = action;
            const agent = state.agents[agentId];
            if (!agent) return state;
            return {
                ...state,
                agents: {
                    ...state.agents,
                    [agentId]: { ...agent, iteration, maxIterations, contextUsage },
                },
            };
        }

        case 'SELECT_AGENT': {
            return { ...state, selectedAgentId: action.agentId };
        }

        case 'RESET': {
            return _INITIAL_STATE;
        }

        default:
            return state;
    }
}

const AgentStateContext = createContext(null);
const AgentDispatchContext = createContext(null);

/**
 * Provider component that wraps the app to make agent state available.
 */
export function AgentStateProvider({ children }) {
    const [state, dispatch] = useReducer(_agentReducer, _INITIAL_STATE);

    return (
        <AgentStateContext.Provider value={state}>
            <AgentDispatchContext.Provider value={dispatch}>
                {children}
            </AgentDispatchContext.Provider>
        </AgentStateContext.Provider>
    );
}

/**
 * Hook to read agent state.
 */
export function useAgentState() {
    const state = useContext(AgentStateContext);
    if (state === null) {
        throw new Error('useAgentState must be used within AgentStateProvider');
    }
    return state;
}

/**
 * Hook to get the dispatch function for agent state actions.
 */
export function useAgentDispatch() {
    const dispatch = useContext(AgentDispatchContext);
    if (dispatch === null) {
        throw new Error('useAgentDispatch must be used within AgentStateProvider');
    }
    return dispatch;
}

/**
 * Returns true if sub-agents exist in the tree (any agent with a parentId).
 */
export function hasSubAgents(state) {
    return Object.values(state.agents).some((a) => a.parentId !== null);
}
