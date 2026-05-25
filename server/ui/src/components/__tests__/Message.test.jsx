import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect } from 'vitest';
import Message from '../Message.jsx';

// Minimal 1x1 transparent PNG
const DATA_URL_PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAADElEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg==';
// Disallowed javascript URL disguised as image
const JS_URL = 'javascript:alert("x")';
// Simple (harmless) SVG turned into data URL
const DATA_URL_SVG = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxIiBoZWlnaHQ9IjEiPjxyZWN0IHdpZHRoPSIxIiBoZWlnaHQ9IjEiIGZpbGw9ImJsYWNrIi8+PC9zdmc+';

/**
 * Assistant messages use `entries` (activity log format) rather than
 * raw `content`. Wrap markdown in a content entry for these tests.
 */
function renderAssistant(markdown) {
    const entries = [{ type: 'content', content: markdown, timestamp: Date.now() }];
    return render(<Message role="assistant" entries={entries} />);
}

function renderUser(markdown) {
    return render(<Message role="user" content={markdown} />);
}

describe('Message markdown image handling', () => {
    it('renders data URL image in assistant message', () => {
        renderAssistant(`Here is an image: ![dot](${DATA_URL_PNG})`);
        const img = screen.getByRole('img', { name: /dot/i });
        expect(img).toBeInTheDocument();
        expect(img.getAttribute('src')).toBe(DATA_URL_PNG);
    });

    it('renders data URL image in user message', () => {
        renderUser(`User image: ![pixel](${DATA_URL_PNG})`);
        const img = screen.getByRole('img', { name: /pixel/i });
        expect(img).toBeInTheDocument();
        expect(img.getAttribute('src')).toBe(DATA_URL_PNG);
    });

    it('blocks javascript: image source', () => {
        renderAssistant(`Bad ref ![bad](${JS_URL})`);
        const img = screen.getByRole('img', { name: /bad/i });
        // urlTransform returns undefined so the src attribute is omitted
        expect(img.getAttribute('src')).toBe(null);
    });

    it('blocks svg data URL image', () => {
        renderAssistant(`Inline svg ![logo](${DATA_URL_SVG})`);
        const img = screen.getByRole('img', { name: /logo/i });
        expect(img.getAttribute('src')).toBe(null);
    });
});

describe('Message user attachments', () => {
    it('renders an image attachment as a thumbnail chip', () => {
        render(<Message role="user" content="look at this" images={[DATA_URL_PNG]} />);
        expect(screen.getByTestId('attachment-image')).toHaveAttribute('src', DATA_URL_PNG);
    });

    it('renders a file attachment as a file card', () => {
        render(<Message role="user" content="" files={[{ filename: 'report.pdf' }]} />);
        expect(screen.getByTestId('attachment-file')).toBeInTheDocument();
        expect(screen.getByText('report.pdf')).toBeInTheDocument();
    });

    it('renders no attachment row when there are none', () => {
        render(<Message role="user" content="just text" />);
        expect(screen.queryByTestId('attachment-image')).not.toBeInTheDocument();
        expect(screen.queryByTestId('attachment-file')).not.toBeInTheDocument();
    });
});

describe('Message spawn card', () => {
    const entries = [
        { type: 'content', content: 'dispatching a sub-agent', timestamp: Date.now() },
        { type: 'spawn_requested', correlationId: 'c-1', timestamp: Date.now() },
        { type: 'content', content: 'sub-agent done', timestamp: Date.now() },
    ];

    it('renders a spawn card inline where the turn spawned agents', () => {
        render(<Message role="assistant" entries={entries} spawnedAgents={[
            { id: 'a1', name: 'coder', status: 'running', correlationId: 'c-1' },
        ]} />);
        expect(screen.getByTestId('spawn-card')).toBeInTheDocument();
        expect(screen.getByText('Coder')).toBeInTheDocument();
    });

    it('renders the spawn card between the surrounding content entries', () => {
        render(<Message role="assistant" entries={entries} spawnedAgents={[
            { id: 'a1', name: 'coder', status: 'running', correlationId: 'c-1' },
        ]} />);
        const bubble = screen.getByTestId('message-assistant');
        const order = [...bubble.querySelectorAll('[data-testid="entry-content"], [data-testid="spawn-card"]')]
            .map((el) => el.getAttribute('data-testid'));
        expect(order).toEqual(['entry-content', 'spawn-card', 'entry-content']);
    });

    it('renders no spawn card when no children match the request', () => {
        render(<Message role="assistant" entries={entries} spawnedAgents={[]} />);
        expect(screen.queryByTestId('spawn-card')).not.toBeInTheDocument();
    });

    it('surfaces resumed spawn_agent tool calls via the activity footer', async () => {
        // Resumed conversations have no spawn_requested entry — just the
        // plain tool_call from history. It's hidden from the inline body
        // and shown in the activity panel.
        const user = userEvent.setup();
        const resumed = [
            { type: 'content', content: 'about to spawn', timestamp: Date.now() },
            { type: 'tool_call', name: 'spawn_agent' },
            { type: 'content', content: 'after', timestamp: Date.now() },
        ];
        render(<Message role="assistant" entries={resumed} />);
        expect(screen.queryByTestId('spawn-card')).not.toBeInTheDocument();
        expect(screen.queryByTestId('entry-tool-call')).not.toBeInTheDocument();
        const toggle = screen.getByTestId('activity-toggle');
        expect(toggle).toHaveTextContent('1 tool');
        await user.click(toggle);
        const panel = screen.getByTestId('activity-panel');
        expect(panel).toHaveTextContent('spawn_agent');
    });

    it('groups consecutive spawn_requested entries into one card', () => {
        const grouped = [
            { type: 'content', content: 'spawning two', timestamp: Date.now() },
            { type: 'spawn_requested', correlationId: 'c-1', timestamp: Date.now() },
            { type: 'spawn_requested', correlationId: 'c-2', timestamp: Date.now() },
            { type: 'content', content: 'both done', timestamp: Date.now() },
            { type: 'spawn_requested', correlationId: 'c-3', timestamp: Date.now() },
            { type: 'content', content: 'third done', timestamp: Date.now() },
        ];
        const agents = [
            { id: 'a1', name: 'coder', status: 'running', correlationId: 'c-1' },
            { id: 'a2', name: 'researcher', status: 'running', correlationId: 'c-2' },
            { id: 'a3', name: 'writer', status: 'running', correlationId: 'c-3' },
        ];
        render(<Message role="assistant" entries={grouped} spawnedAgents={agents} />);
        const cards = screen.getAllByTestId('spawn-card');
        expect(cards).toHaveLength(2);
        expect(cards[0]).toHaveTextContent('2 agents');
        expect(cards[0]).toHaveTextContent('Coder');
        expect(cards[0]).toHaveTextContent('Researcher');
        expect(cards[1]).toHaveTextContent('1 agent');
        expect(cards[1]).toHaveTextContent('Writer');
    });
});

describe('Message ephemeral status and activity footer', () => {
    it('shows ephemeral row while streaming when last entry is thinking', () => {
        const entries = [
            { type: 'content', content: 'starting', timestamp: 1 },
            { type: 'thinking', thinking: 'planning the next step', timestamp: 2 },
        ];
        render(<Message role="assistant" entries={entries} streaming />);
        const eph = screen.getByTestId('ephemeral-status');
        expect(eph).toHaveTextContent('Thinking…');
    });

    it('shows ephemeral with tool name when last entry is a tool_call', () => {
        const entries = [
            { type: 'content', content: 'about to look', timestamp: 1 },
            { type: 'tool_call', name: 'run_bash_cmd', arguments: { cmd: 'ls' }, timestamp: 2 },
        ];
        render(<Message role="assistant" entries={entries} streaming />);
        expect(screen.getByTestId('ephemeral-status')).toHaveTextContent('Calling run_bash_cmd…');
    });

    it('shows Thinking… ephemeral row when streaming with no entries yet', () => {
        // Brand-new assistant turn: stream is open but nothing has arrived.
        // The ephemeral row is the only thing in the bubble.
        render(<Message role="assistant" entries={[]} streaming />);
        expect(screen.getByTestId('ephemeral-status')).toHaveTextContent('Thinking…');
    });

    it('renders nothing when not streaming and there are no entries', () => {
        render(<Message role="assistant" entries={[]} />);
        expect(screen.queryByTestId('ephemeral-status')).not.toBeInTheDocument();
        expect(screen.queryByTestId('activity-toggle')).not.toBeInTheDocument();
    });

    it('hides ephemeral while streaming when last entry is visible content', () => {
        const entries = [
            { type: 'thinking', thinking: '...', timestamp: 1 },
            { type: 'tool_call', name: 'run_bash_cmd', timestamp: 2 },
            { type: 'content', content: 'here is the answer', timestamp: 3 },
        ];
        render(<Message role="assistant" entries={entries} streaming />);
        expect(screen.queryByTestId('ephemeral-status')).not.toBeInTheDocument();
    });

    it('hides thinking and raw tool_call entries from the inline body', () => {
        const entries = [
            { type: 'thinking', thinking: 'private thoughts', timestamp: 1 },
            { type: 'tool_call', name: 'run_bash_cmd', arguments: { cmd: 'ls' }, timestamp: 2 },
            { type: 'content', content: 'visible content', timestamp: 3 },
        ];
        render(<Message role="assistant" entries={entries} />);
        const bubble = screen.getByTestId('message-assistant');
        expect(bubble).toHaveTextContent('visible content');
        expect(bubble.querySelector('[data-testid="entry-tool-call"]')).toBeNull();
        expect(bubble.querySelector('[data-testid="entry-thinking"]')).toBeNull();
        expect(bubble).not.toHaveTextContent('private thoughts');
    });

    it('shows the activity footer once streaming is done', () => {
        const entries = [
            { type: 'thinking', thinking: 't1', timestamp: 1 },
            { type: 'tool_call', name: 'run_bash_cmd', timestamp: 2 },
            { type: 'thinking', thinking: 't2', timestamp: 3 },
            { type: 'content', content: 'done', timestamp: 4 },
        ];
        render(<Message role="assistant" entries={entries} />);
        const toggle = screen.getByTestId('activity-toggle');
        expect(toggle).toHaveTextContent('Show activity');
        expect(toggle).toHaveTextContent('1 tool');
        expect(toggle).toHaveTextContent('2 thoughts');
    });

    it('does not render the activity footer while streaming', () => {
        const entries = [
            { type: 'thinking', thinking: 't1', timestamp: 1 },
            { type: 'tool_call', name: 'run_bash_cmd', timestamp: 2 },
        ];
        render(<Message role="assistant" entries={entries} streaming />);
        expect(screen.queryByTestId('activity-toggle')).not.toBeInTheDocument();
    });

    it('does not render the activity footer when there is no hidden activity', () => {
        const entries = [{ type: 'content', content: 'just text', timestamp: 1 }];
        render(<Message role="assistant" entries={entries} />);
        expect(screen.queryByTestId('activity-toggle')).not.toBeInTheDocument();
    });

    it('counts spawn_agent tool calls toward the tool tally', () => {
        // spawn_agent calls are stored in the activityLog as both a
        // tool_call (for the panel + count) AND a spawn_requested (for
        // the SpawnCard). The footer count uses tool_call entries.
        const entries = [
            { type: 'thinking', thinking: 'planning', timestamp: 1 },
            { type: 'tool_call', name: 'spawn_agent', arguments: { agent_name: 'A' }, timestamp: 2 },
            { type: 'spawn_requested', correlationId: 'c-1', timestamp: 3 },
            { type: 'tool_call', name: 'spawn_agent', arguments: { agent_name: 'B' }, timestamp: 4 },
            { type: 'spawn_requested', correlationId: 'c-2', timestamp: 5 },
            { type: 'tool_call', name: 'run_bash_cmd', timestamp: 6 },
            { type: 'content', content: 'done', timestamp: 7 },
        ];
        render(<Message role="assistant" entries={entries} />);
        const toggle = screen.getByTestId('activity-toggle');
        // 2 spawn_agent + 1 run_bash_cmd = 3 tools
        expect(toggle).toHaveTextContent('3 tools');
        expect(toggle).toHaveTextContent('1 thought');
    });

    it('surfaces spawn_agent rows in the expanded activity panel', async () => {
        const user = userEvent.setup();
        const entries = [
            { type: 'tool_call', name: 'spawn_agent', arguments: { agent_name: 'WORKER' }, timestamp: 1 },
            { type: 'spawn_requested', correlationId: 'c-1', timestamp: 2 },
            { type: 'content', content: 'spawned', timestamp: 3 },
        ];
        render(<Message role="assistant" entries={entries} />);
        await user.click(screen.getByTestId('activity-toggle'));
        const panel = screen.getByTestId('activity-panel');
        expect(panel).toHaveTextContent('spawn_agent');
        expect(panel).toHaveTextContent('agent_name="WORKER"');
    });

    it('clicking the footer reveals the activity panel with all hidden entries', async () => {
        const user = userEvent.setup();
        const entries = [
            { type: 'thinking', thinking: 'first thought', timestamp: 1 },
            { type: 'tool_call', name: 'run_bash_cmd', arguments: { cmd: 'ls' }, timestamp: 2 },
            { type: 'thinking', thinking: 'second thought', timestamp: 3 },
            { type: 'content', content: 'answer', timestamp: 4 },
        ];
        render(<Message role="assistant" entries={entries} />);
        expect(screen.queryByTestId('activity-panel')).not.toBeInTheDocument();

        await user.click(screen.getByTestId('activity-toggle'));
        const panel = screen.getByTestId('activity-panel');
        expect(panel).toHaveTextContent('first thought');
        expect(panel).toHaveTextContent('second thought');
        expect(panel).toHaveTextContent('run_bash_cmd');
        expect(panel).toHaveTextContent('cmd="ls"');

        // Toggling again hides the panel
        await user.click(screen.getByTestId('activity-toggle'));
        expect(screen.queryByTestId('activity-panel')).not.toBeInTheDocument();
    });
});
