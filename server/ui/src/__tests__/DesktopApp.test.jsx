import { render, screen, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { AgentStateProvider, useAgentState, useAgentDispatch } from '../hooks/useAgentState.jsx';

// Minimal 1x1 transparent PNG
const TINY_PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAADElEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg==';

// ── Mock heavy child components ─────────────────────────────────────
// We only care about which panels / views are mounted, not their internals.

vi.mock('../components/Header.jsx', () => ({
    default: () => <div data-testid="header">Header</div>,
}));

vi.mock('../components/ChatPanel.jsx', () => ({
    default: ({ networkActivated, networkAgentCount, onOpenNetwork }) => (
        <div data-testid="chat-panel">
            Chat
            {networkActivated && (
                <button data-testid="network-indicator" onClick={onOpenNetwork}>
                    {networkAgentCount} agents
                </button>
            )}
        </div>
    ),
}));

vi.mock('../components/BrowserPreview.jsx', () => ({
    default: ({ snapshot }) => snapshot
        ? <div data-testid="browser-preview">Browser: {snapshot.url}</div>
        : null,
}));

vi.mock('../components/TerminalOutput.jsx', () => ({
    default: ({ lines }) => lines?.length
        ? <div data-testid="terminal-panel">Terminal ({lines.length} cmds)</div>
        : null,
}));

vi.mock('../components/DesktopPreview.jsx', () => ({
    default: ({ visible }) => visible
        ? <div data-testid="desktop-preview">Desktop</div>
        : null,
}));

vi.mock('../components/GenerationPreview.jsx', () => ({
    default: ({ preview }) => preview
        ? <div data-testid="generation-preview">Generation: {preview.status}</div>
        : null,
}));

vi.mock('../components/AgentNetwork.jsx', () => ({
    default: ({ onClose }) => (
        <div data-testid="agent-network">
            Network Graph
            {onClose && <button data-testid="network-close" onClick={onClose}>Close</button>}
        </div>
    ),
}));

vi.mock('../components/AgentActivityView.jsx', () => ({
    default: () => <div data-testid="agent-activity-view">Activity View</div>,
}));

vi.mock('../components/Sidebar.jsx', () => ({
    default: () => <div data-testid="sidebar">Sidebar</div>,
}));

vi.mock('../components/FlyoutPanel.jsx', () => ({
    default: () => null,
}));

vi.mock('../components/PreviewPanel.jsx', () => ({
    default: ({ children }) => <div data-testid="preview-panel">{children}</div>,
}));

vi.mock('../components/SplitHandle.jsx', () => ({
    default: () => <div data-testid="split-handle" />,
}));

vi.mock('../components/FilePreviewInline.jsx', () => ({
    default: ({ item }) => <div data-testid="file-preview-inline">{item?.filename}</div>,
}));

vi.mock('../components/FileFullscreen.jsx', () => ({
    default: () => <div data-testid="fullscreen-preview" />,
}));

vi.mock('../components/BrowserFullscreen.jsx', () => ({
    default: () => <div data-testid="browser-fullscreen" />,
}));

vi.mock('../components/SettingsPage.jsx', () => ({
    default: () => <div data-testid="settings-page">Settings</div>,
}));

vi.mock('../components/SystemSettings.jsx', () => ({
    default: () => <div>SystemSettings</div>,
}));

vi.mock('../components/ProfilesTab.jsx', () => ({
    default: () => <div>ProfilesTab</div>,
}));

vi.mock('../components/SetupWizard.jsx', () => ({
    default: () => <div data-testid="setup-wizard">Setup Wizard</div>,
}));

vi.mock('../hooks/useAgentProfiles.js', () => ({
    default: () => ({
        profiles: [],
        selectedProfileId: null,
        setSelectedProfileId: vi.fn(),
        createProfile: vi.fn(),
        updateProfile: vi.fn(),
        deleteProfile: vi.fn(),
        duplicateProfile: vi.fn(),
        revision: 0,
    }),
}));

vi.mock('../hooks/useStreamingChat.js', () => ({
    default: () => ({
        messages: [],
        isStreaming: false,
        sendMessage: vi.fn(),
        stopGeneration: vi.fn(),
        loadConversation: vi.fn(),
        newConversation: vi.fn(),
    }),
}));

vi.mock('../hooks/useModelSettings.js', () => ({
    default: () => ({
        selectedModel: 'test',
        contextKb: '',
        think: false,
        temperature: '',
        topK: '',
        topP: '',
        repeatPenalty: '',
        numPredict: '',
    }),
}));

vi.mock('../components/ToastProvider.jsx', () => ({
    useToast: () => ({ addToast: vi.fn() }),
}));

// ── Import after mocks ──────────────────────────────────────────────
// Dynamic import so vi.mock calls are hoisted before it runs.
const { default: DesktopApp } = await import('../DesktopApp.jsx');

/**
 * DesktopApp wraps itself in AgentStateProvider, so we render it
 * directly and reach in via a side-channel to dispatch state changes.
 *
 * We render a companion Inspector inside the same provider to get
 * dispatch. DesktopApp creates its own provider though, so we need
 * to work around that — we'll dispatch from outside by re-rendering.
 *
 * Actually, DesktopApp creates its own AgentStateProvider internally.
 * So we need to access the dispatch from inside. We do this by
 * intercepting the useAgentDispatch calls via the mock system.
 */

// We'll capture dispatch from inside DesktopApp by patching into the
// AgentStateProvider. Instead, let's test the view logic by directly
// testing the inner component with a provider we control.

/**
 * Since DesktopApp creates its own provider, we test the view selection
 * logic by rendering DesktopApp and using the stream callbacks to drive
 * state changes. The mocked useStreamingChat gives us access to the
 * callbacks that DesktopApp passes to it.
 *
 * Alternatively, we can test the layout logic more directly by
 * extracting the state→view mapping. But to keep it end-to-end,
 * we'll capture the dispatch from inside the component tree.
 */

let capturedDispatch = null;

// Re-mock useAgentState hooks to capture dispatch
vi.mock('../hooks/useAgentState.jsx', async (importOriginal) => {
    const actual = await importOriginal();
    return {
        ...actual,
        useAgentDispatch: () => {
            const dispatch = actual.useAgentDispatch();
            capturedDispatch = dispatch;
            return dispatch;
        },
    };
});

async function renderApp() {
    capturedDispatch = null;
    let result;
    await act(async () => {
        result = render(<DesktopApp dark={false} onToggleTheme={vi.fn()} />);
    });

    const dispatch = (action) => {
        act(() => capturedDispatch(action));
    };

    return { dispatch, ...result };
}

function startRoot(dispatch, id, { name = 'computron' } = {}) {
    dispatch({
        type: 'AGENT_STARTED',
        agentId: id,
        agentName: name,
        parentAgentId: null,
        instruction: '',
        timestamp: Date.now(),
    });
}

function startSubAgent(dispatch, id, parentId, { name = 'browser_agent' } = {}) {
    dispatch({
        type: 'AGENT_STARTED',
        agentId: id,
        agentName: name,
        parentAgentId: parentId,
        instruction: '',
        timestamp: Date.now(),
    });
}

// ─────────────────────────────────────────────────────────────────────

describe('DesktopApp view transitions', () => {
    beforeEach(() => {
        capturedDispatch = null;
        // Mock fetch for /api/settings and /api/models so the setup wizard resolves
        globalThis.fetch = vi.fn((url) => {
            if (url === '/api/settings') {
                return Promise.resolve({ json: () => Promise.resolve({ setup_complete: true }) });
            }
            if (url === '/api/models') {
                return Promise.resolve({ json: () => Promise.resolve({ models: [] }) });
            }
            return Promise.resolve({ json: () => Promise.resolve({}) });
        });
    });

    // ── Simple chat view (no sub-agents, no previews) ───────────────

    describe('simple chat view', () => {
        it('shows chat panel on initial render', async () => {
            await renderApp();
            expect(screen.getByTestId('chat-panel')).toBeInTheDocument();
        });

        it('does not show network graph initially', async () => {
            await renderApp();
            expect(screen.queryByTestId('agent-network')).not.toBeInTheDocument();
        });

        it('does not show activity view initially', async () => {
            await renderApp();
            expect(screen.queryByTestId('agent-activity-view')).not.toBeInTheDocument();
        });
    });

    // ── Simple chat + preview panels ────────────────────────────────

    describe('simple chat with preview panels', () => {
        it('shows browser preview alongside chat when snapshot arrives', async () => {
            const { dispatch } = await renderApp();
            startRoot(dispatch, 'r1');
            dispatch({
                type: 'UPDATE_BROWSER_SNAPSHOT',
                agentId: 'r1',
                snapshot: { url: 'https://test.com', title: 'Test', screenshot: TINY_PNG },
            });

            expect(screen.getByTestId('chat-panel')).toBeInTheDocument();
            expect(screen.getByTestId('browser-preview')).toBeInTheDocument();
        });

        it('shows terminal panel alongside chat', async () => {
            const { dispatch } = await renderApp();
            startRoot(dispatch, 'r1');
            dispatch({
                type: 'UPDATE_TERMINAL',
                agentId: 'r1',
                event: { cmd_id: 'c1', cmd: 'ls', stdout: 'out\n', status: 'complete' },
            });

            expect(screen.getByTestId('chat-panel')).toBeInTheDocument();
            expect(screen.getByTestId('terminal-panel')).toBeInTheDocument();
        });

        it('shows generation preview alongside chat', async () => {
            const { dispatch } = await renderApp();
            startRoot(dispatch, 'r1');
            dispatch({
                type: 'UPDATE_GENERATION_PREVIEW',
                agentId: 'r1',
                preview: { gen_id: 'g1', media_type: 'image', status: 'generating', step: 5, total_steps: 20 },
            });

            expect(screen.getByTestId('chat-panel')).toBeInTheDocument();
            expect(screen.getByTestId('generation-preview')).toBeInTheDocument();
        });

        it('previews persist into second turn', async () => {
            const { dispatch } = await renderApp();
            startRoot(dispatch, 'r1');
            dispatch({
                type: 'UPDATE_BROWSER_SNAPSHOT',
                agentId: 'r1',
                snapshot: { url: 'https://test.com', title: 'Test', screenshot: TINY_PNG },
            });

            expect(screen.getByTestId('browser-preview')).toBeInTheDocument();

            // Second turn — new root agent
            startRoot(dispatch, 'r2');

            // Browser preview should still be visible (carried over)
            expect(screen.getByTestId('browser-preview')).toBeInTheDocument();
        });

        it('terminal lines persist into second turn', async () => {
            const { dispatch } = await renderApp();
            startRoot(dispatch, 'r1');
            dispatch({
                type: 'UPDATE_TERMINAL',
                agentId: 'r1',
                event: { cmd_id: 'c1', cmd: 'ls', stdout: 'out\n', status: 'complete' },
            });

            expect(screen.getByTestId('terminal-panel')).toBeInTheDocument();

            startRoot(dispatch, 'r2');
            expect(screen.getByTestId('terminal-panel')).toBeInTheDocument();
        });

        it('generation preview persists into second turn', async () => {
            const { dispatch } = await renderApp();
            startRoot(dispatch, 'r1');
            dispatch({
                type: 'UPDATE_GENERATION_PREVIEW',
                agentId: 'r1',
                preview: { gen_id: 'g1', media_type: 'image', status: 'complete' },
            });

            expect(screen.getByTestId('generation-preview')).toBeInTheDocument();

            startRoot(dispatch, 'r2');
            expect(screen.getByTestId('generation-preview')).toBeInTheDocument();
        });

        it('new browser snapshot replaces old one in second turn', async () => {
            const { dispatch } = await renderApp();
            startRoot(dispatch, 'r1');
            dispatch({
                type: 'UPDATE_BROWSER_SNAPSHOT',
                agentId: 'r1',
                snapshot: { url: 'https://first.com', title: 'First', screenshot: TINY_PNG },
            });

            startRoot(dispatch, 'r2');
            dispatch({
                type: 'UPDATE_BROWSER_SNAPSHOT',
                agentId: 'r2',
                snapshot: { url: 'https://second.com', title: 'Second', screenshot: TINY_PNG },
            });

            expect(screen.getByText('Browser: https://second.com')).toBeInTheDocument();
        });
    });

    // ── Network view (sub-agents) ───────────────────────────────────

    describe('network view', () => {
        it('does not auto-show network when sub-agent spawns; shows indicator instead', async () => {
            const { dispatch } = await renderApp();
            startRoot(dispatch, 'r1');
            startSubAgent(dispatch, 's1', 'r1');

            // Network is NOT auto-shown — chat stays visible
            expect(screen.queryByTestId('agent-network')).not.toBeInTheDocument();
            expect(screen.getByTestId('chat-panel')).toBeInTheDocument();
            // Indicator appears so user can navigate to network
            expect(screen.getByTestId('network-indicator')).toBeInTheDocument();
        });

        it('shows network when indicator is clicked', async () => {
            const { dispatch } = await renderApp();
            startRoot(dispatch, 'r1');
            startSubAgent(dispatch, 's1', 'r1');

            act(() => fireEvent.click(screen.getByTestId('network-indicator')));

            expect(screen.getByTestId('agent-network')).toBeInTheDocument();
        });

        it('closes network and returns to chat', async () => {
            const { dispatch } = await renderApp();
            startRoot(dispatch, 'r1');
            startSubAgent(dispatch, 's1', 'r1');

            act(() => fireEvent.click(screen.getByTestId('network-indicator')));
            expect(screen.getByTestId('agent-network')).toBeInTheDocument();

            act(() => fireEvent.click(screen.getByTestId('network-close')));
            expect(screen.queryByTestId('agent-network')).not.toBeInTheDocument();
            expect(screen.getByTestId('chat-panel')).toBeInTheDocument();
        });

        it('does not show preview column when network view is open', async () => {
            const { dispatch } = await renderApp();
            startRoot(dispatch, 'r1');
            dispatch({
                type: 'UPDATE_BROWSER_SNAPSHOT',
                agentId: 'r1',
                snapshot: { url: 'https://test.com', title: 'Test', screenshot: TINY_PNG },
            });
            expect(screen.getByTestId('browser-preview')).toBeInTheDocument();

            startSubAgent(dispatch, 's1', 'r1');
            act(() => fireEvent.click(screen.getByTestId('network-indicator')));

            // Network is shown, preview column is hidden
            expect(screen.getByTestId('agent-network')).toBeInTheDocument();
            expect(screen.queryByTestId('browser-preview')).not.toBeInTheDocument();
        });

        it('previews return when network view is closed', async () => {
            const { dispatch } = await renderApp();
            startRoot(dispatch, 'r1');
            dispatch({
                type: 'UPDATE_BROWSER_SNAPSHOT',
                agentId: 'r1',
                snapshot: { url: 'https://test.com', title: 'Test', screenshot: TINY_PNG },
            });

            startSubAgent(dispatch, 's1', 'r1');
            act(() => fireEvent.click(screen.getByTestId('network-indicator')));
            expect(screen.queryByTestId('browser-preview')).not.toBeInTheDocument();

            act(() => fireEvent.click(screen.getByTestId('network-close')));
            expect(screen.getByTestId('browser-preview')).toBeInTheDocument();
        });
    });

    // ── Detail view (agent selected) ────────────────────────────────

    describe('detail view', () => {
        it('shows activity view when agent is selected from network view', async () => {
            const { dispatch } = await renderApp();
            startRoot(dispatch, 'r1');
            startSubAgent(dispatch, 's1', 'r1');

            // Open network first, then select agent
            act(() => fireEvent.click(screen.getByTestId('network-indicator')));
            dispatch({ type: 'SELECT_AGENT', agentId: 's1' });

            expect(screen.getByTestId('agent-activity-view')).toBeInTheDocument();
        });

        it('does not show activity view when agent is selected but network is closed', async () => {
            const { dispatch } = await renderApp();
            startRoot(dispatch, 'r1');
            startSubAgent(dispatch, 's1', 'r1');

            // Select without opening network — should not show activity view
            dispatch({ type: 'SELECT_AGENT', agentId: 's1' });
            expect(screen.queryByTestId('agent-activity-view')).not.toBeInTheDocument();
        });

        it('returns to network view when selection is cleared', async () => {
            const { dispatch } = await renderApp();
            startRoot(dispatch, 'r1');
            startSubAgent(dispatch, 's1', 'r1');

            act(() => fireEvent.click(screen.getByTestId('network-indicator')));
            dispatch({ type: 'SELECT_AGENT', agentId: 's1' });
            expect(screen.getByTestId('agent-activity-view')).toBeInTheDocument();

            dispatch({ type: 'SELECT_AGENT', agentId: null });
            expect(screen.queryByTestId('agent-activity-view')).not.toBeInTheDocument();
            expect(screen.getByTestId('agent-network')).toBeInTheDocument();
        });
    });

    // ── Full lifecycle ──────────────────────────────────────────────

    describe('full lifecycle transitions', () => {
        it('simple chat → preview → open network → detail → back to network → close → chat with previews', async () => {
            const { dispatch } = await renderApp();

            // 1. Start in simple chat
            expect(screen.getByTestId('chat-panel')).toBeInTheDocument();
            expect(screen.queryByTestId('agent-network')).not.toBeInTheDocument();

            // 2. Root agent starts, browser snapshot appears → preview column
            startRoot(dispatch, 'r1');
            dispatch({
                type: 'UPDATE_BROWSER_SNAPSHOT',
                agentId: 'r1',
                snapshot: { url: 'https://test.com', title: 'Test', screenshot: TINY_PNG },
            });
            expect(screen.getByTestId('browser-preview')).toBeInTheDocument();

            // 3. Sub-agent spawns → indicator appears, chat + preview still visible
            startSubAgent(dispatch, 's1', 'r1');
            expect(screen.getByTestId('chat-panel')).toBeInTheDocument();
            expect(screen.getByTestId('browser-preview')).toBeInTheDocument();
            expect(screen.getByTestId('network-indicator')).toBeInTheDocument();

            // 4. Click indicator → network view (chat + preview hidden)
            act(() => fireEvent.click(screen.getByTestId('network-indicator')));
            expect(screen.getByTestId('agent-network')).toBeInTheDocument();
            expect(screen.queryByTestId('browser-preview')).not.toBeInTheDocument();

            // 5. Select sub-agent → detail view
            dispatch({ type: 'SELECT_AGENT', agentId: 's1' });
            expect(screen.getByTestId('agent-activity-view')).toBeInTheDocument();
            expect(screen.queryByTestId('agent-network')).not.toBeInTheDocument();

            // 6. Deselect → back to network
            dispatch({ type: 'SELECT_AGENT', agentId: null });
            expect(screen.getByTestId('agent-network')).toBeInTheDocument();
            expect(screen.queryByTestId('agent-activity-view')).not.toBeInTheDocument();

            // 7. Close network → back to chat with previews
            act(() => fireEvent.click(screen.getByTestId('network-close')));
            expect(screen.getByTestId('chat-panel')).toBeInTheDocument();
            expect(screen.getByTestId('browser-preview')).toBeInTheDocument();
            expect(screen.queryByTestId('agent-network')).not.toBeInTheDocument();
        });
    });
});
