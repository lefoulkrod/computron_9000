import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import RecentConversations from '../RecentConversations.jsx';

function isoAgo({ days = 0, hours = 0 }) {
    const d = new Date();
    d.setDate(d.getDate() - days);
    d.setHours(d.getHours() - hours);
    return d.toISOString();
}

// A spread of conversations across the day buckets.
const SESSIONS = [
    { conversation_id: 'c1', title: 'muxer flush bug', started_at: isoAgo({ hours: 1 }) },
    { conversation_id: 'c2', title: 'snake game', started_at: isoAgo({ hours: 3 }) },
    { conversation_id: 'c3', title: 'release notes draft', started_at: isoAgo({ days: 1 }) },
    { conversation_id: 'c4', title: 'eval pass', started_at: isoAgo({ days: 6 }) },
];

function mockFetch(sessions = SESSIONS) {
    global.fetch = vi.fn((url, opts) => {
        if (opts?.method === 'DELETE') {
            return Promise.resolve({ ok: true, status: 204 });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve(sessions) });
    });
}

beforeEach(() => mockFetch());
afterEach(() => vi.restoreAllMocks());

describe('RecentConversations', () => {
    it('lists fetched conversations grouped by day', async () => {
        render(<RecentConversations onLoadConversation={vi.fn()} />);
        await waitFor(() => expect(screen.getAllByTestId('recent-item')).toHaveLength(4));
        expect(screen.getByText('Today')).toBeInTheDocument();
        expect(screen.getByText('Yesterday')).toBeInTheDocument();
        expect(screen.getByText('Earlier')).toBeInTheDocument();
    });

    it('filters the list by the search query', async () => {
        const user = userEvent.setup();
        render(<RecentConversations onLoadConversation={vi.fn()} />);
        await waitFor(() => expect(screen.getAllByTestId('recent-item')).toHaveLength(4));

        await user.type(screen.getByTestId('recent-search'), 'snake');
        expect(screen.getAllByTestId('recent-item')).toHaveLength(1);
        expect(screen.getByText('snake game')).toBeInTheDocument();
    });

    it('shows a no-matches message when the search excludes everything', async () => {
        const user = userEvent.setup();
        render(<RecentConversations onLoadConversation={vi.fn()} />);
        await waitFor(() => expect(screen.getAllByTestId('recent-item')).toHaveLength(4));

        await user.type(screen.getByTestId('recent-search'), 'zzzznomatch');
        expect(screen.getByTestId('recent-empty')).toHaveTextContent('No matches');
    });

    it('loads a conversation when its row is clicked', async () => {
        const user = userEvent.setup();
        const onLoadConversation = vi.fn();
        render(<RecentConversations onLoadConversation={onLoadConversation} />);
        await waitFor(() => expect(screen.getAllByTestId('recent-item')).toHaveLength(4));

        await user.click(screen.getByText('muxer flush bug'));
        expect(onLoadConversation).toHaveBeenCalledWith('c1');
    });

    it('deletes a conversation without loading it', async () => {
        const user = userEvent.setup();
        const onLoadConversation = vi.fn();
        render(<RecentConversations onLoadConversation={onLoadConversation} />);
        await waitFor(() => expect(screen.getAllByTestId('recent-item')).toHaveLength(4));

        const firstRow = screen.getAllByTestId('recent-item')[0];
        await user.click(firstRow.querySelector('[data-testid="recent-delete"]'));

        await waitFor(() => expect(screen.getAllByTestId('recent-item')).toHaveLength(3));
        expect(onLoadConversation).not.toHaveBeenCalled();
        expect(global.fetch).toHaveBeenCalledWith(
            '/api/conversations/sessions/c1',
            expect.objectContaining({ method: 'DELETE' }),
        );
    });

    it('marks the active conversation', async () => {
        render(<RecentConversations onLoadConversation={vi.fn()} activeConversationId="c2" />);
        await waitFor(() => expect(screen.getAllByTestId('recent-item')).toHaveLength(4));
        const active = screen.getByText('snake game').closest('[data-testid="recent-item"]');
        expect(active).toHaveAttribute('data-conversation-id', 'c2');
        expect(active.className).toMatch(/active/);
    });

    it('shows an empty state when there are no conversations', async () => {
        mockFetch([]);
        render(<RecentConversations onLoadConversation={vi.fn()} />);
        await waitFor(() => expect(screen.getByTestId('recent-empty')).toBeInTheDocument());
        expect(screen.getByTestId('recent-empty')).toHaveTextContent('No conversations yet');
    });

    it('falls back to the first message when a conversation has no title', async () => {
        mockFetch([{ conversation_id: 'c9', first_message: 'hello there', started_at: isoAgo({ hours: 1 }) }]);
        render(<RecentConversations onLoadConversation={vi.fn()} />);
        await waitFor(() => expect(screen.getByText('hello there')).toBeInTheDocument());
    });
});
