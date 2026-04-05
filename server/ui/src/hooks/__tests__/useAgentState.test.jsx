import { render, screen, act } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { AgentStateProvider, useAgentState, useAgentDispatch } from '../useAgentState.jsx';

/**
 * Helper that renders a component inside the AgentStateProvider and
 * exposes dispatch + a live snapshot of state via refs.
 */
function renderWithProvider() {
    let dispatch;
    let state;

    function Inspector() {
        state = useAgentState();
        dispatch = useAgentDispatch();
        return null;
    }

    render(
        <AgentStateProvider>
            <Inspector />
        </AgentStateProvider>,
    );

    return {
        getState: () => state,
        dispatch: (action) => act(() => dispatch(action)),
    };
}

// ── Helpers to build common actions ─────────────────────────────────

function agentStarted(agentId, { name = 'root', parentAgentId = null, instruction = '' } = {}) {
    return {
        type: 'AGENT_STARTED',
        agentId,
        agentName: name,
        parentAgentId,
        instruction,
        timestamp: Date.now(),
    };
}

function agentCompleted(agentId, status = 'success') {
    return { type: 'AGENT_COMPLETED', agentId, status };
}

const BROWSER_SNAPSHOT = {
    url: 'https://example.com',
    title: 'Example',
    screenshot: 'AAAA',
    agentId: 'root-1',
};

const TERMINAL_EVENT = {
    cmd_id: 'cmd-1',
    cmd: 'echo hello',
    stdout: 'hello\n',
    stderr: null,
    exit_code: 0,
    status: 'complete',
    agentId: 'root-1',
};

const GENERATION_PREVIEW = {
    gen_id: 'gen-1',
    media_type: 'image',
    status: 'generating',
    step: 5,
    total_steps: 20,
    agentId: 'root-1',
};

// ─────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────

describe('useAgentState reducer', () => {
    // ── Preview carryover across turns ──────────────────────────────

    describe('preview carryover between turns', () => {
        it('carries browser snapshot from previous root to new root', () => {
            const { getState, dispatch } = renderWithProvider();

            dispatch(agentStarted('root-1'));
            dispatch({ type: 'UPDATE_BROWSER_SNAPSHOT', agentId: 'root-1', snapshot: BROWSER_SNAPSHOT });

            // New turn — new root agent
            dispatch(agentStarted('root-2'));

            const newRoot = getState().agents['root-2'];
            expect(newRoot.browserSnapshot).toEqual(BROWSER_SNAPSHOT);
        });

        it('carries terminal lines from previous root to new root', () => {
            const { getState, dispatch } = renderWithProvider();

            dispatch(agentStarted('root-1'));
            dispatch({ type: 'UPDATE_TERMINAL', agentId: 'root-1', event: TERMINAL_EVENT });

            dispatch(agentStarted('root-2'));

            const newRoot = getState().agents['root-2'];
            expect(newRoot.terminalLines).toHaveLength(1);
            expect(newRoot.terminalLines[0].cmd).toBe('echo hello');
        });

        it('carries desktopActive from previous root to new root', () => {
            const { getState, dispatch } = renderWithProvider();

            dispatch(agentStarted('root-1'));
            dispatch({ type: 'UPDATE_DESKTOP_ACTIVE', agentId: 'root-1' });

            dispatch(agentStarted('root-2'));

            expect(getState().agents['root-2'].desktopActive).toBe(true);
        });

        it('carries generation preview from previous root to new root', () => {
            const { getState, dispatch } = renderWithProvider();

            dispatch(agentStarted('root-1'));
            dispatch({ type: 'UPDATE_GENERATION_PREVIEW', agentId: 'root-1', preview: GENERATION_PREVIEW });

            dispatch(agentStarted('root-2'));

            expect(getState().agents['root-2'].generationPreview).toEqual(GENERATION_PREVIEW);
        });

        it('new preview data replaces carried-over data in new turn', () => {
            const { getState, dispatch } = renderWithProvider();

            dispatch(agentStarted('root-1'));
            dispatch({ type: 'UPDATE_BROWSER_SNAPSHOT', agentId: 'root-1', snapshot: BROWSER_SNAPSHOT });

            dispatch(agentStarted('root-2'));

            const newSnapshot = { ...BROWSER_SNAPSHOT, url: 'https://new.com', agentId: 'root-2' };
            dispatch({ type: 'UPDATE_BROWSER_SNAPSHOT', agentId: 'root-2', snapshot: newSnapshot });

            expect(getState().agents['root-2'].browserSnapshot.url).toBe('https://new.com');
        });

        it('terminal lines are appended in new turn (not reset)', () => {
            const { getState, dispatch } = renderWithProvider();

            dispatch(agentStarted('root-1'));
            dispatch({ type: 'UPDATE_TERMINAL', agentId: 'root-1', event: TERMINAL_EVENT });

            dispatch(agentStarted('root-2'));
            dispatch({
                type: 'UPDATE_TERMINAL',
                agentId: 'root-2',
                event: { ...TERMINAL_EVENT, cmd_id: 'cmd-2', cmd: 'ls', agentId: 'root-2' },
            });

            expect(getState().agents['root-2'].terminalLines).toHaveLength(2);
        });
    });

    // ── Network activation ──────────────────────────────────────────

    describe('network activation', () => {
        it('networkActivated is false initially', () => {
            const { getState } = renderWithProvider();
            expect(getState().networkActivated).toBe(false);
        });

        it('networkActivated becomes true when a sub-agent appears', () => {
            const { getState, dispatch } = renderWithProvider();

            dispatch(agentStarted('root-1'));
            expect(getState().networkActivated).toBe(false);

            dispatch(agentStarted('sub-1', { name: 'browser', parentAgentId: 'root-1' }));
            expect(getState().networkActivated).toBe(true);
        });

        it('networkActivated stays true across new turns', () => {
            const { getState, dispatch } = renderWithProvider();

            dispatch(agentStarted('root-1'));
            dispatch(agentStarted('sub-1', { name: 'browser', parentAgentId: 'root-1' }));
            expect(getState().networkActivated).toBe(true);

            // New root-only turn
            dispatch(agentStarted('root-2'));
            expect(getState().networkActivated).toBe(true);
        });

        it('networkActivated resets on RESET', () => {
            const { getState, dispatch } = renderWithProvider();

            dispatch(agentStarted('root-1'));
            dispatch(agentStarted('sub-1', { name: 'browser', parentAgentId: 'root-1' }));
            dispatch({ type: 'RESET' });

            expect(getState().networkActivated).toBe(false);
        });
    });

    // ── Generation preview replacement ──────────────────────────────

    describe('generation preview', () => {
        it('merges progress updates with same gen_id', () => {
            const { getState, dispatch } = renderWithProvider();

            dispatch(agentStarted('root-1'));
            dispatch({ type: 'UPDATE_GENERATION_PREVIEW', agentId: 'root-1', preview: GENERATION_PREVIEW });
            dispatch({
                type: 'UPDATE_GENERATION_PREVIEW',
                agentId: 'root-1',
                preview: { ...GENERATION_PREVIEW, step: 10 },
            });

            expect(getState().agents['root-1'].generationPreview.step).toBe(10);
            expect(getState().agents['root-1'].generationPreview.gen_id).toBe('gen-1');
        });

        it('replaces preview when gen_id differs', () => {
            const { getState, dispatch } = renderWithProvider();

            dispatch(agentStarted('root-1'));
            dispatch({ type: 'UPDATE_GENERATION_PREVIEW', agentId: 'root-1', preview: GENERATION_PREVIEW });
            dispatch({
                type: 'UPDATE_GENERATION_PREVIEW',
                agentId: 'root-1',
                preview: { ...GENERATION_PREVIEW, gen_id: 'gen-2', step: 1 },
            });

            expect(getState().agents['root-1'].generationPreview.gen_id).toBe('gen-2');
            expect(getState().agents['root-1'].generationPreview.step).toBe(1);
        });
    });

    // ── Root and selected agent transitions ─────────────────────────

    describe('agent selection and root transitions', () => {
        it('new root clears selectedAgentId', () => {
            const { getState, dispatch } = renderWithProvider();

            dispatch(agentStarted('root-1'));
            dispatch(agentStarted('sub-1', { name: 'browser', parentAgentId: 'root-1' }));
            dispatch({ type: 'SELECT_AGENT', agentId: 'sub-1' });
            expect(getState().selectedAgentId).toBe('sub-1');

            // New turn resets selection
            dispatch(agentStarted('root-2'));
            expect(getState().selectedAgentId).toBeNull();
        });

        it('sub-agent start does not change rootId', () => {
            const { getState, dispatch } = renderWithProvider();

            dispatch(agentStarted('root-1'));
            dispatch(agentStarted('sub-1', { name: 'browser', parentAgentId: 'root-1' }));

            expect(getState().rootId).toBe('root-1');
        });

        it('sub-agent start does not clear selectedAgentId', () => {
            const { getState, dispatch } = renderWithProvider();

            dispatch(agentStarted('root-1'));
            dispatch({ type: 'SELECT_AGENT', agentId: 'root-1' });
            dispatch(agentStarted('sub-1', { name: 'browser', parentAgentId: 'root-1' }));

            expect(getState().selectedAgentId).toBe('root-1');
        });

        it('AGENT_COMPLETED sets status and clears activeTool', () => {
            const { getState, dispatch } = renderWithProvider();

            dispatch(agentStarted('root-1'));
            dispatch({ type: 'UPDATE_ACTIVE_TOOL', agentId: 'root-1', toolName: 'browse_page' });
            dispatch(agentCompleted('root-1', 'success'));

            const agent = getState().agents['root-1'];
            expect(agent.status).toBe('success');
            expect(agent.activeTool).toBeNull();
        });
    });
});
