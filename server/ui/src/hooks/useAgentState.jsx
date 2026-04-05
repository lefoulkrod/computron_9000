import { createContext, useContext, useReducer } from 'react';
import { mergeTerminalEvent } from '../utils/agentUtils.js';

/**
 * State for the agent tree. This powers the network graph and agent
 * detail views. Each agent gets its own node with activity log,
 * browser screenshots, terminal output, etc.
 *
 * Data arrives here via:
 *   backend stream → useStreamingChat → DesktopApp callbacks → dispatch
 *
 * The tree builds up as agent_started events arrive and updates as
 * content tokens, tool calls, and screenshots flow in.
 */
const _INITIAL_STATE = {
    agents: {},             // all agent nodes, keyed by ID
    rootId: null,           // the top-level agent
    selectedAgentId: null,  // which card the user clicked into
    networkActivated: false, // true once any sub-agent appears; stays true for the conversation
};

/**
 * Create a fresh agent node with all the data an agent card or
 * detail view might need.
 */
function _makeAgent(id, name, parentId, instruction, startedAt) {
    return {
        id,
        name,
        parentId,
        status: 'running',       // running | success | error | stopped
        childIds: [],            // sub-agents spawned by this agent
        startedAt,               // for elapsed time display
        instruction: instruction || '',
        activityLog: [],         // everything the agent did: thinking, content, tool calls
        browserSnapshot: null,   // latest screenshot (shown as card thumbnail too)
        terminalLines: [],       // bash output
        desktopActive: false,
        generationPreview: null,
        activeTool: null,        // what tool is running right now
        completedAt: null,       // when the agent finished (for frozen elapsed time)
        iteration: null,         // current loop iteration
        maxIterations: null,     // budget limit
        contextUsage: null,      // how full the context window is
    };
}

/**
 * All agent state changes go through this reducer. The action names
 * map pretty directly to what happened:
 *
 *   AGENT_STARTED/COMPLETED → agent appeared or finished
 *   APPEND_STREAM_CHUNK     → new text from a sub-agent
 *   APPEND_ACTIVITY         → tool call or file output happened
 *   UPDATE_*                → preview data changed (screenshot, terminal, etc.)
 *   SELECT_AGENT            → user clicked a card
 *   RESET                   → new conversation
 */
function _agentReducer(state, action) {
    switch (action.type) {
        // New agent appeared — create its node and wire it to its parent.
        case 'AGENT_STARTED': {
            const { agentId, agentName, parentAgentId, instruction, timestamp } = action;
            const agent = _makeAgent(agentId, agentName, parentAgentId, instruction, timestamp);

            // When a new root agent starts (new turn), carry over persistent
            // preview state so panels don't vanish between turns. Previews are
            // only replaced by newer data or appended to (terminal).
            if (!parentAgentId && state.rootId && state.agents[state.rootId]) {
                const prev = state.agents[state.rootId];
                agent.browserSnapshot = prev.browserSnapshot;
                agent.terminalLines = prev.terminalLines;
                agent.desktopActive = prev.desktopActive;
                agent.generationPreview = prev.generationPreview;
            }

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
                // Always update rootId when a new root agent starts (no parent).
                // Each turn creates a fresh root span with a new ID, so the
                // simple chat view needs to follow the latest one.
                // Clear selectedAgentId so we don't stay stuck in an old
                // agent's detail view when a new turn begins.
                rootId: parentAgentId ? state.rootId : agentId,
                selectedAgentId: parentAgentId ? state.selectedAgentId : null,
                // Once a sub-agent appears, network view stays active for the
                // rest of the conversation. Only RESET clears this.
                networkActivated: state.networkActivated || !!parentAgentId,
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
                    [agentId]: { ...agent, status, activeTool: null, completedAt: Date.now() },
                },
            };
        }

        // Append streamed text to an agent's activity log. Thinking and
        // content are merged in one update to keep them from getting
        // interleaved. If the last log entry is the same type, we just
        // extend it instead of creating a new one.
        case 'APPEND_STREAM_CHUNK': {
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

        // Add a one-off entry (tool call, file output) to the activity log.
        // Consecutive content/thinking entries get merged together.
        case 'APPEND_ACTIVITY': {
            const { agentId, entry } = action;
            const agent = state.agents[agentId];
            if (!agent) return state;
            const log = agent.activityLog;
            const last = log.length > 0 ? log[log.length - 1] : null;
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
            // Merge with existing preview if same gen_id, otherwise replace
            const existing = agent.generationPreview;
            const merged = (existing && existing.gen_id === preview.gen_id)
                ? { ...existing, ...preview }
                : preview;
            return {
                ...state,
                agents: {
                    ...state.agents,
                    [agentId]: { ...agent, generationPreview: merged },
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
