import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import MemoryTab from '../MemoryTab.jsx';

const _mockEntries = {
    user_name: 'Larry Foulkrod',
    user_email: 'larry@example.com',
    user_phone: '555-0100',
};

function _mockFetchOnce(body, init = { status: 200 }) {
    return Promise.resolve({
        ok: init.status >= 200 && init.status < 300,
        status: init.status,
        json: async () => body,
    });
}

describe('MemoryTab', () => {
    let _originalFetch;
    let _fetchCalls;

    beforeEach(() => {
        _originalFetch = global.fetch;
        _fetchCalls = [];
        global.fetch = vi.fn((url, init) => {
            _fetchCalls.push({ url, init });
            if (url === '/api/memory' && (!init || init.method === undefined || init.method === 'GET')) {
                return _mockFetchOnce({ entries: _mockEntries, hidden: ['user_phone'] });
            }
            if (url.startsWith('/api/memory/') && init?.method === 'DELETE') {
                return _mockFetchOnce({}, { status: 204 });
            }
            if (url.endsWith('/hidden') && init?.method === 'POST') {
                return _mockFetchOnce({});
            }
            return _mockFetchOnce({}, { status: 404 });
        });
    });

    afterEach(() => {
        global.fetch = _originalFetch;
    });

    it('renders one row per memory with the full value', async () => {
        render(<MemoryTab />);
        await waitFor(() => expect(screen.getAllByTestId('memory-row')).toHaveLength(3));
        expect(screen.getByText('user_name')).toBeInTheDocument();
        expect(screen.getByText('Larry Foulkrod')).toBeInTheDocument();
        expect(screen.getByText('larry@example.com')).toBeInTheDocument();
    });

    it('masks the value when the entry is flagged hidden', async () => {
        render(<MemoryTab />);
        await waitFor(() => expect(screen.getAllByTestId('memory-row')).toHaveLength(3));
        const hiddenRow = document.querySelector('[data-key="user_phone"]');
        expect(hiddenRow.querySelector('[data-testid="memory-value"]')).toHaveTextContent('••••••••');
        expect(hiddenRow.querySelector('[data-testid="memory-hide"]')).toHaveAttribute('aria-pressed', 'true');
    });

    it('toggling hide masks the value and POSTs the new state', async () => {
        const user = userEvent.setup();
        render(<MemoryTab />);
        await waitFor(() => expect(screen.getAllByTestId('memory-row')).toHaveLength(3));

        const row = document.querySelector('[data-key="user_email"]');
        const hideBtn = row.querySelector('[data-testid="memory-hide"]');
        const valueCell = row.querySelector('[data-testid="memory-value"]');
        expect(valueCell).toHaveTextContent('larry@example.com');

        await user.click(hideBtn);
        expect(valueCell).toHaveTextContent('••••••••');
        expect(hideBtn).toHaveAttribute('aria-pressed', 'true');

        const hideCall = _fetchCalls.find((c) => c.url === '/api/memory/user_email/hidden');
        expect(hideCall).toBeDefined();
        expect(hideCall.init.method).toBe('POST');
        expect(JSON.parse(hideCall.init.body)).toEqual({ hidden: true });
    });

    it('deletes a memory and removes its row', async () => {
        const user = userEvent.setup();
        render(<MemoryTab />);
        await waitFor(() => expect(screen.getAllByTestId('memory-row')).toHaveLength(3));

        const row = document.querySelector('[data-key="user_name"]');
        const delBtn = row.querySelector('[data-testid="memory-delete"]');
        await user.click(delBtn);

        await waitFor(() => expect(screen.queryByText('user_name')).not.toBeInTheDocument());
        const delCall = _fetchCalls.find((c) => c.url === '/api/memory/user_name' && c.init?.method === 'DELETE');
        expect(delCall).toBeDefined();
    });

    it('shows the empty state when there are no memories', async () => {
        global.fetch = vi.fn(() => _mockFetchOnce({ entries: {}, hidden: [] }));
        render(<MemoryTab />);
        await waitFor(() => expect(screen.getByText('No memories yet.')).toBeInTheDocument());
        expect(screen.queryByTestId('memory-row')).not.toBeInTheDocument();
    });
});
