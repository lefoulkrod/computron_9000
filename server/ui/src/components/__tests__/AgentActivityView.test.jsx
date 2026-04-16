import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { AgentStateProvider, useAgentDispatch } from '../../hooks/useAgentState.jsx';
import AgentActivityView from '../AgentActivityView.jsx';
import { act } from 'react';

// ── Mock child components that are hard to render in jsdom ───────────

vi.mock('../DesktopPreview.jsx', () => ({
    default: ({ visible }) => visible ? <div data-testid="desktop-preview">Desktop</div> : null,
}));

// ── Helpers ──────────────────────────────────────────────────────────

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

    describe('activity pane', () => {
        it('always has activityFull class (previews are in shared panel)', () => {
            const { dispatch, container } = renderView();
            startAgent(dispatch, 'a1');

            const activity = container.querySelector('[class*="activity"]');
            expect(activity.className).toMatch(/activityFull/);
        });

        it('stays full width even when preview data exists on agent', () => {
            const { dispatch, container } = renderView();
            startAgent(dispatch, 'a1');
            dispatch({
                type: 'UPDATE_BROWSER_SNAPSHOT',
                agentId: 'a1',
                snapshot: { url: 'https://example.com', title: 'Example', screenshot: 'abc' },
            });

            const activity = container.querySelector('[class*="activity"]');
            expect(activity.className).toMatch(/activityFull/);
        });
    });

    describe('does not render inline previews', () => {
        it('no previews div exists', () => {
            const { dispatch, container } = renderView();
            startAgent(dispatch, 'a1');
            dispatch({
                type: 'UPDATE_BROWSER_SNAPSHOT',
                agentId: 'a1',
                snapshot: { url: 'https://example.com', title: 'Example', screenshot: 'abc' },
            });

            const previews = container.querySelector('[class*="previews"]');
            expect(previews).toBeNull();
        });
    });

    describe('file outputs in activity stream', () => {
        it('renders file outputs via AgentOutput when showFileOutputs is true', () => {
            const { dispatch } = renderView();
            startAgent(dispatch, 'a1');
            dispatch({
                type: 'APPEND_ACTIVITY',
                agentId: 'a1',
                entry: { type: 'file_output', filename: 'report.html', content_type: 'text/html', content: 'abc' },
            });

            expect(screen.getByText('report.html')).toBeInTheDocument();
        });
    });

    describe('transitions', () => {
        it('shows running cursor while agent is running', () => {
            const { dispatch, container } = renderView();
            startAgent(dispatch, 'a1');

            expect(container.querySelector('[class*="cursor"]')).toBeInTheDocument();

            dispatch({ type: 'AGENT_COMPLETED', agentId: 'a1', status: 'success' });

            expect(container.querySelector('[class*="cursor"]')).not.toBeInTheDocument();
        });
    });
});
