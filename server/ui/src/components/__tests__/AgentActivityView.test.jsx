import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { AgentStateProvider, useAgentDispatch } from '../../hooks/useAgentState.jsx';
import AgentActivityView from '../AgentActivityView.jsx';
import { act } from 'react';

// Minimal 1x1 transparent PNG so BrowserPreview renders an <img>
const TINY_PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAADElEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg==';

// ── Mock child components that are hard to render in jsdom ───────────

vi.mock('../DesktopPreview.jsx', () => ({
    default: ({ visible }) => visible ? <div data-testid="desktop-preview">Desktop</div> : null,
}));

// ── Helpers ──────────────────────────────────────────────────────────

/**
 * Wraps AgentActivityView in the state provider and returns a dispatch
 * function so tests can drive state changes.
 */
function renderView() {
    let dispatch;

    function Harness() {
        dispatch = useAgentDispatch();
        return <AgentActivityView onNudge={vi.fn()} onPreview={vi.fn()} />;
    }

    const result = render(
        <AgentStateProvider>
            <Harness />
        </AgentStateProvider>,
    );

    return {
        dispatch: (action) => act(() => dispatch(action)),
        ...result,
    };
}

function startAgent(dispatch, id, { name = 'computron', parent = null, instruction = '' } = {}) {
    dispatch({
        type: 'AGENT_STARTED',
        agentId: id,
        agentName: name,
        parentAgentId: parent,
        instruction,
        timestamp: Date.now(),
    });
    dispatch({ type: 'SELECT_AGENT', agentId: id });
}

// ─────────────────────────────────────────────────────────────────────

describe('AgentActivityView', () => {
    it('renders nothing when no agent is selected', () => {
        const { container } = render(
            <AgentStateProvider>
                <AgentActivityView onNudge={vi.fn()} onPreview={vi.fn()} />
            </AgentStateProvider>,
        );
        expect(container.innerHTML).toBe('');
    });

    it('renders agent name and instruction', () => {
        const { dispatch } = renderView();
        startAgent(dispatch, 'a1', { instruction: 'Go to example.com' });

        expect(screen.getAllByText('Computron')).toHaveLength(2); // breadcrumb + title
        expect(screen.getByText('Go to example.com')).toBeInTheDocument();
    });

    // ── Activity pane expands when no previews ──────────────────────

    describe('activity pane width', () => {
        it('has activityFull class when no previews exist', () => {
            const { dispatch, container } = renderView();
            startAgent(dispatch, 'a1');

            const activity = container.querySelector('[class*="activity"]');
            expect(activity.className).toMatch(/activityFull/);
        });

        it('does NOT have activityFull class when browser preview exists', () => {
            const { dispatch, container } = renderView();
            startAgent(dispatch, 'a1');
            dispatch({
                type: 'UPDATE_BROWSER_SNAPSHOT',
                agentId: 'a1',
                snapshot: { url: 'https://example.com', title: 'Example', screenshot: TINY_PNG },
            });

            const activity = container.querySelector('[class*="activity"]');
            expect(activity.className).not.toMatch(/activityFull/);
        });

        it('does NOT have activityFull class when terminal output exists', () => {
            const { dispatch, container } = renderView();
            startAgent(dispatch, 'a1');
            dispatch({
                type: 'UPDATE_TERMINAL',
                agentId: 'a1',
                event: { cmd_id: 'c1', cmd: 'ls', stdout: 'file.txt\n', status: 'complete' },
            });

            const activity = container.querySelector('[class*="activity"]');
            expect(activity.className).not.toMatch(/activityFull/);
        });

        it('does NOT have activityFull class when desktop is active', () => {
            const { dispatch, container } = renderView();
            startAgent(dispatch, 'a1');
            dispatch({ type: 'UPDATE_DESKTOP_ACTIVE', agentId: 'a1' });

            const activity = container.querySelector('[class*="activity"]');
            expect(activity.className).not.toMatch(/activityFull/);
        });

        it('does NOT have activityFull class when generation preview exists', () => {
            const { dispatch, container } = renderView();
            startAgent(dispatch, 'a1');
            dispatch({
                type: 'UPDATE_GENERATION_PREVIEW',
                agentId: 'a1',
                preview: { gen_id: 'g1', media_type: 'image', status: 'generating', step: 1, total_steps: 10 },
            });

            const activity = container.querySelector('[class*="activity"]');
            expect(activity.className).not.toMatch(/activityFull/);
        });
    });

    // ── Preview panels render ───────────────────────────────────────

    describe('preview panels', () => {
        it('does not render previews div when no preview data', () => {
            const { dispatch, container } = renderView();
            startAgent(dispatch, 'a1');

            // The previews div has a border-left — should not be present
            const previews = container.querySelector('[class*="previews"]');
            expect(previews).toBeNull();
        });

        it('renders browser preview when snapshot exists', () => {
            const { dispatch } = renderView();
            startAgent(dispatch, 'a1');
            dispatch({
                type: 'UPDATE_BROWSER_SNAPSHOT',
                agentId: 'a1',
                snapshot: { url: 'https://example.com', title: 'Example Page', screenshot: TINY_PNG },
            });

            expect(screen.getByText('Browser')).toBeInTheDocument();
            expect(screen.getByText('https://example.com')).toBeInTheDocument();
        });

        it('renders terminal panel when lines exist', () => {
            const { dispatch } = renderView();
            startAgent(dispatch, 'a1');
            dispatch({
                type: 'UPDATE_TERMINAL',
                agentId: 'a1',
                event: { cmd_id: 'c1', cmd: 'echo hello', stdout: 'hello\n', status: 'complete', exit_code: 0 },
            });

            expect(screen.getByText('Terminal')).toBeInTheDocument();
            expect(screen.getByText('echo hello')).toBeInTheDocument();
        });

        it('renders desktop preview when active', () => {
            const { dispatch } = renderView();
            startAgent(dispatch, 'a1');
            dispatch({ type: 'UPDATE_DESKTOP_ACTIVE', agentId: 'a1' });

            expect(screen.getByTestId('desktop-preview')).toBeInTheDocument();
        });

        it('renders generation preview when present', () => {
            const { dispatch } = renderView();
            startAgent(dispatch, 'a1');
            dispatch({
                type: 'UPDATE_GENERATION_PREVIEW',
                agentId: 'a1',
                preview: { gen_id: 'g1', media_type: 'image', status: 'generating', step: 5, total_steps: 20 },
            });

            expect(screen.getByText('Generating Image')).toBeInTheDocument();
        });

        it('renders multiple preview panels simultaneously', () => {
            const { dispatch } = renderView();
            startAgent(dispatch, 'a1');

            dispatch({
                type: 'UPDATE_BROWSER_SNAPSHOT',
                agentId: 'a1',
                snapshot: { url: 'https://example.com', title: 'Example', screenshot: TINY_PNG },
            });
            dispatch({
                type: 'UPDATE_TERMINAL',
                agentId: 'a1',
                event: { cmd_id: 'c1', cmd: 'ls', stdout: 'out\n', status: 'complete', exit_code: 0 },
            });

            expect(screen.getByText('Browser')).toBeInTheDocument();
            expect(screen.getByText('Terminal')).toBeInTheDocument();
        });
    });

    // ── Transitions ─────────────────────────────────────────────────

    describe('transitions', () => {
        it('activity pane transitions from full to split when preview appears', () => {
            const { dispatch, container } = renderView();
            startAgent(dispatch, 'a1');

            const activity = container.querySelector('[class*="activity"]');
            expect(activity.className).toMatch(/activityFull/);

            dispatch({
                type: 'UPDATE_BROWSER_SNAPSHOT',
                agentId: 'a1',
                snapshot: { url: 'https://example.com', title: 'Example', screenshot: TINY_PNG },
            });

            expect(activity.className).not.toMatch(/activityFull/);
        });

        it('shows running cursor while agent is running', () => {
            const { dispatch, container } = renderView();
            startAgent(dispatch, 'a1');

            expect(container.querySelector('[class*="cursor"]')).toBeInTheDocument();

            dispatch({ type: 'AGENT_COMPLETED', agentId: 'a1', status: 'success' });

            expect(container.querySelector('[class*="cursor"]')).not.toBeInTheDocument();
        });
    });
});
