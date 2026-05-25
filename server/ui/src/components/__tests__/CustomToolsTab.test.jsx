import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import CustomToolsTab from '../CustomToolsTab.jsx';

const _mockTools = [
    {
        id: 't1', name: 'fetch_page', description: 'Fetch a URL and return text',
        type: 'program', language: 'python',
    },
    {
        id: 't2', name: 'ls_home', description: 'List home dir',
        type: 'command', language: 'bash',
    },
    {
        id: 't3', name: 'count_lines', description: 'Count lines in a file',
        type: 'program', language: 'bash',
    },
];

function _ok(body) {
    return Promise.resolve({ ok: true, status: 200, json: async () => body });
}
function _noContent() {
    return Promise.resolve({ ok: true, status: 204, json: async () => ({}) });
}

describe('CustomToolsTab', () => {
    let _originalFetch;
    let _calls;

    beforeEach(() => {
        _originalFetch = global.fetch;
        _calls = [];
        global.fetch = vi.fn((url, init) => {
            _calls.push({ url, init });
            if (url === '/api/custom-tools' && (!init || init.method === undefined)) {
                return _ok(_mockTools);
            }
            if (url.startsWith('/api/custom-tools/') && init?.method === 'DELETE') {
                return _noContent();
            }
            return _ok({});
        });
    });

    afterEach(() => {
        global.fetch = _originalFetch;
    });

    it('renders one row per tool with name and description', async () => {
        render(<CustomToolsTab />);
        await waitFor(() => expect(screen.getAllByTestId('custom-tools-row')).toHaveLength(3));
        expect(screen.getByText('fetch_page')).toBeInTheDocument();
        expect(screen.getByText('Fetch a URL and return text')).toBeInTheDocument();
        expect(screen.getByText('ls_home')).toBeInTheDocument();
        expect(screen.getByText('count_lines')).toBeInTheDocument();
    });

    it('shows the right badge label per tool type/language', async () => {
        render(<CustomToolsTab />);
        await waitFor(() => expect(screen.getAllByTestId('custom-tools-row')).toHaveLength(3));
        const fetchRow = document.querySelector('[data-tool-name="fetch_page"]');
        const lsRow = document.querySelector('[data-tool-name="ls_home"]');
        const countRow = document.querySelector('[data-tool-name="count_lines"]');
        expect(fetchRow).toHaveTextContent('python');
        // Command type wins over language
        expect(lsRow).toHaveTextContent('cmd');
        expect(countRow).toHaveTextContent('bash');
    });

    it('deletes a tool and removes its row', async () => {
        const user = userEvent.setup();
        render(<CustomToolsTab />);
        await waitFor(() => expect(screen.getAllByTestId('custom-tools-row')).toHaveLength(3));

        const row = document.querySelector('[data-tool-name="ls_home"]');
        await user.click(row.querySelector('[data-testid="custom-tools-delete"]'));

        await waitFor(() => expect(screen.queryByText('ls_home')).not.toBeInTheDocument());
        const delCall = _calls.find((c) => c.url === '/api/custom-tools/ls_home' && c.init?.method === 'DELETE');
        expect(delCall).toBeDefined();
    });

    it('shows the empty state when there are no tools', async () => {
        global.fetch = vi.fn(() => _ok([]));
        render(<CustomToolsTab />);
        await waitFor(() => expect(screen.getByText('No custom tools defined.')).toBeInTheDocument());
        expect(screen.queryByTestId('custom-tools-row')).not.toBeInTheDocument();
    });
});
