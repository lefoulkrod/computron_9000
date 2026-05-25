import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import ActivityRail from '../ActivityRail.jsx';

describe('ActivityRail', () => {
    it('renders nothing for empty entries', () => {
        const { container } = render(<ActivityRail entries={[]} />);
        expect(container).toBeEmptyDOMElement();
    });

    it('renders each entry type as its own row', () => {
        const entries = [
            { type: 'thinking', thinking: 'planning the work' },
            { type: 'content', content: 'here is the answer' },
            { type: 'tool_call', name: 'read_file', arguments: { path: 'foo.py' } },
        ];
        render(<ActivityRail entries={entries} />);
        expect(screen.getByTestId('activity-row-thinking')).toBeInTheDocument();
        expect(screen.getByTestId('activity-row-content')).toBeInTheDocument();
        expect(screen.getByTestId('activity-row-tool')).toBeInTheDocument();
    });

    it('renders thinking text inside the thinking row', () => {
        render(<ActivityRail entries={[{ type: 'thinking', thinking: 'planning the work' }]} />);
        expect(screen.getByText('planning the work')).toBeInTheDocument();
    });

    it('renders tool call as a function-call signature with the first arg shown', () => {
        const entries = [{
            type: 'tool_call',
            name: 'read_file',
            arguments: { path: 'PLAN.md' },
        }];
        render(<ActivityRail entries={entries} />);
        const row = screen.getByTestId('activity-tool-call');
        expect(row).toHaveTextContent('read_file');
        expect(row).toHaveTextContent('path=');
        expect(row).toHaveTextContent('"PLAN.md"');
    });

    it('shows ellipsis for multi-arg tool calls', () => {
        const entries = [{
            type: 'tool_call',
            name: 'replace_in_file',
            arguments: { path: 'foo.py', old: 'a', new: 'b' },
        }];
        render(<ActivityRail entries={entries} />);
        const row = screen.getByTestId('activity-tool-call');
        expect(row).toHaveTextContent('path=');
        expect(row).toHaveTextContent('"foo.py"');
        expect(row).toHaveTextContent('…');
        // Other args aren't on the collapsed line
        expect(row.textContent).not.toMatch(/old=/);
    });

    it('clicking the tool row expands the full args panel', async () => {
        const user = userEvent.setup();
        const entries = [{
            type: 'tool_call',
            name: 'replace_in_file',
            arguments: { path: 'foo.py', old: 'old text', new: 'new text' },
        }];
        render(<ActivityRail entries={entries} />);
        expect(screen.queryByTestId('activity-tool-detail')).not.toBeInTheDocument();

        await user.click(screen.getByTestId('activity-tool-call'));
        const detail = screen.getByTestId('activity-tool-detail');
        expect(detail).toHaveTextContent('path');
        expect(detail).toHaveTextContent('"foo.py"');
        expect(detail).toHaveTextContent('old');
        expect(detail).toHaveTextContent('"old text"');
        expect(detail).toHaveTextContent('new');
        expect(detail).toHaveTextContent('"new text"');

        // Toggling again collapses
        await user.click(screen.getByTestId('activity-tool-call'));
        expect(screen.queryByTestId('activity-tool-detail')).not.toBeInTheDocument();
    });

    it('renders consecutive tool_call entries on a rail-joined row', () => {
        const entries = [
            { type: 'tool_call', name: 'read_file', arguments: { path: 'a.py' } },
            { type: 'tool_call', name: 'read_file', arguments: { path: 'b.py' } },
            { type: 'tool_call', name: 'read_file', arguments: { path: 'c.py' } },
        ];
        render(<ActivityRail entries={entries} />);
        const rows = screen.getAllByTestId('activity-row-tool');
        expect(rows).toHaveLength(3);
        // First row has a visible marker; the next rows are joined and skip it
        expect(rows[0].querySelector('[aria-hidden="true"]')).not.toBeNull();
    });

    it('renders a spawn card for spawn_requested entries with matching children', () => {
        const entries = [
            { type: 'spawn_requested', correlationId: 'c-1' },
        ];
        const spawnedAgents = [
            { id: 'a1', name: 'coder', status: 'running', correlationId: 'c-1' },
        ];
        render(<ActivityRail entries={entries} spawnedAgents={spawnedAgents} />);
        expect(screen.getByTestId('activity-row-spawn')).toBeInTheDocument();
        expect(screen.getByTestId('spawn-card')).toBeInTheDocument();
        expect(screen.getByText('Coder')).toBeInTheDocument();
    });

    it('clicking a spawn card row fires onSelectAgent', async () => {
        const user = userEvent.setup();
        const onSelectAgent = vi.fn();
        const entries = [{ type: 'spawn_requested', correlationId: 'c-1' }];
        const spawnedAgents = [
            { id: 'a9', name: 'coder', status: 'running', correlationId: 'c-1' },
        ];
        render(<ActivityRail entries={entries} spawnedAgents={spawnedAgents} onSelectAgent={onSelectAgent} />);
        await user.click(screen.getByTestId('spawn-card-row'));
        expect(onSelectAgent).toHaveBeenCalledWith('a9');
    });

    it('renders no spawn row when there is no matching child', () => {
        const entries = [{ type: 'spawn_requested', correlationId: 'c-1' }];
        render(<ActivityRail entries={entries} spawnedAgents={[]} />);
        expect(screen.queryByTestId('activity-row-spawn')).not.toBeInTheDocument();
    });

    it('groups consecutive spawn_requested entries into one card row', () => {
        const entries = [
            { type: 'spawn_requested', correlationId: 'c-1' },
            { type: 'spawn_requested', correlationId: 'c-2' },
            { type: 'content', content: 'between' },
            { type: 'spawn_requested', correlationId: 'c-3' },
        ];
        const spawnedAgents = [
            { id: 'a1', name: 'coder', status: 'running', correlationId: 'c-1' },
            { id: 'a2', name: 'researcher', status: 'running', correlationId: 'c-2' },
            { id: 'a3', name: 'writer', status: 'running', correlationId: 'c-3' },
        ];
        render(<ActivityRail entries={entries} spawnedAgents={spawnedAgents} />);
        const spawnRows = screen.getAllByTestId('activity-row-spawn');
        expect(spawnRows).toHaveLength(2);
    });

    it('renders file_output entries inline', () => {
        const entries = [
            { type: 'file_output', filename: 'report.html', content_type: 'text/html' },
        ];
        render(<ActivityRail entries={entries} onPreview={vi.fn()} />);
        expect(screen.getByTestId('activity-row-file')).toBeInTheDocument();
        expect(screen.getByText('report.html')).toBeInTheDocument();
    });

    it('does not render spawn_agent tool_call as a tool row (SpawnCard handles it)', () => {
        // Both entries land in the activityLog for the same action.
        // The SpawnCard renders via spawn_requested; the raw tool_call
        // row is skipped so the action isn't duplicated.
        const entries = [
            { type: 'tool_call', name: 'spawn_agent', arguments: { agent_name: 'WORKER' } },
            { type: 'spawn_requested', correlationId: 'c-1' },
        ];
        const spawnedAgents = [
            { id: 'a1', name: 'worker', status: 'running', correlationId: 'c-1' },
        ];
        render(<ActivityRail entries={entries} spawnedAgents={spawnedAgents} />);
        // Only the spawn row exists, no tool row
        expect(screen.getByTestId('activity-row-spawn')).toBeInTheDocument();
        expect(screen.queryByTestId('activity-row-tool')).not.toBeInTheDocument();
        // The function-call line for spawn_agent isn't drawn
        expect(screen.queryByTestId('activity-tool-call')).not.toBeInTheDocument();
    });

    it('groups non-spawn tool calls separately when a spawn_agent sits between', () => {
        const entries = [
            { type: 'tool_call', name: 'read_file', arguments: { path: 'a.py' } },
            { type: 'tool_call', name: 'spawn_agent', arguments: { agent_name: 'X' } },
            { type: 'spawn_requested', correlationId: 'c-1' },
            { type: 'tool_call', name: 'read_file', arguments: { path: 'b.py' } },
        ];
        const spawnedAgents = [
            { id: 'x', name: 'x', status: 'running', correlationId: 'c-1' },
        ];
        render(<ActivityRail entries={entries} spawnedAgents={spawnedAgents} />);
        // Two non-spawn tool rows, separated by the spawn card — neither
        // should be a "joined" row (each gets its own rail marker).
        const toolRows = screen.getAllByTestId('activity-row-tool');
        expect(toolRows).toHaveLength(2);
    });
});
