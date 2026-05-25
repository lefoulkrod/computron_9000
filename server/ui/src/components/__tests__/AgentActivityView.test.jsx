import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

    describe('spawn card', () => {
        function spawnChildren(dispatch) {
            startAgent(dispatch, 'a1');
            dispatch({
                type: 'APPEND_ACTIVITY',
                agentId: 'a1',
                entry: { type: 'spawn_requested', correlationId: 'c-1' },
            });
            dispatch({
                type: 'APPEND_ACTIVITY',
                agentId: 'a1',
                entry: { type: 'spawn_requested', correlationId: 'c-2' },
            });
            dispatch({
                type: 'AGENT_STARTED', agentId: 'c1', agentName: 'research_agent',
                parentAgentId: 'a1', instruction: '', correlationId: 'c-1', timestamp: Date.now(),
            });
            dispatch({
                type: 'AGENT_STARTED', agentId: 'c2', agentName: 'code_expert',
                parentAgentId: 'a1', instruction: '', correlationId: 'c-2', timestamp: Date.now(),
            });
            dispatch({ type: 'SELECT_AGENT', agentId: 'a1' });
        }

        it('renders an inline spawn card for the agent\'s sub-agents', () => {
            const { dispatch } = renderView();
            spawnChildren(dispatch);

            expect(screen.getByTestId('spawn-card')).toBeInTheDocument();
            expect(screen.getAllByTestId('spawn-card-row')).toHaveLength(2);
        });

        it('clicking a spawn card row switches the view to that sub-agent', () => {
            const { dispatch } = renderView();
            spawnChildren(dispatch);

            act(() => {
                screen.getAllByTestId('spawn-card-row')[0].click();
            });
            expect(screen.getByTestId('agent-activity-title')).toHaveTextContent('Research Agent');
        });

        it('renders no spawn card when the agent spawned nothing', () => {
            const { dispatch } = renderView();
            startAgent(dispatch, 'a1');
            expect(screen.queryByTestId('spawn-card')).not.toBeInTheDocument();
        });
    });

describe('collapsible instruction', () => {
        it('starts collapsed — body is hidden, preview shows the first line', () => {
            const { dispatch } = renderView();
            startAgent(dispatch, 'a1', {
                instruction: 'First line summary\n\nLonger detail that should only appear when expanded.',
            });

            // Toggle visible, body hidden
            expect(screen.getByTestId('instruction-toggle')).toBeInTheDocument();
            expect(screen.queryByTestId('instruction-body')).not.toBeInTheDocument();

            // Preview shows the first line
            expect(screen.getByTestId('instruction-toggle')).toHaveTextContent('First line summary');
            // Longer detail isn't visible when collapsed
            expect(screen.queryByText(/Longer detail/)).not.toBeInTheDocument();
        });

        it('clicking the toggle expands the full instruction body', async () => {
            const user = userEvent.setup();
            const { dispatch } = renderView();
            startAgent(dispatch, 'a1', {
                instruction: 'First line\n\nFull detail here.',
            });

            await user.click(screen.getByTestId('instruction-toggle'));
            const body = screen.getByTestId('instruction-body');
            expect(body).toHaveTextContent('First line');
            expect(body).toHaveTextContent('Full detail here.');

            // Toggling again collapses
            await user.click(screen.getByTestId('instruction-toggle'));
            expect(screen.queryByTestId('instruction-body')).not.toBeInTheDocument();
        });

        it('does not render the instruction bar when there is no instruction', () => {
            const { dispatch } = renderView();
            startAgent(dispatch, 'a1', { instruction: '' });
            expect(screen.queryByTestId('instruction-toggle')).not.toBeInTheDocument();
        });
    });
});
