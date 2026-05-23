import { render, screen } from '@testing-library/react';
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

    it('renders raw spawn_agent tool-call line on the resume path', () => {
        // Resumed conversations have no spawn_requested entry — just the
        // plain tool_call from history. It should render as a raw line.
        const resumed = [
            { type: 'content', content: 'about to spawn', timestamp: Date.now() },
            { type: 'tool_call', name: 'spawn_agent' },
            { type: 'content', content: 'after', timestamp: Date.now() },
        ];
        render(<Message role="assistant" entries={resumed} />);
        expect(screen.queryByTestId('spawn-card')).not.toBeInTheDocument();
        const toolCalls = screen.getAllByTestId('entry-tool-call');
        expect(toolCalls.some((el) => el.textContent.includes('spawn_agent'))).toBe(true);
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
