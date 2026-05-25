import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import SpawnCard from '../SpawnCard.jsx';

const agent = (over = {}) => ({
    id: 'a1',
    name: 'coder',
    status: 'running',
    iteration: 3,
    maxIterations: 12,
    contextUsage: { context_used: 4200, context_limit: 32000 },
    ...over,
});

describe('SpawnCard', () => {
    it('renders nothing without agents', () => {
        const { container } = render(<SpawnCard agents={[]} onSelectAgent={vi.fn()} />);
        expect(container).toBeEmptyDOMElement();
    });

    it('renders a row per agent with the formatted name', () => {
        render(<SpawnCard
            agents={[agent({ id: 'a1', name: 'coder' }), agent({ id: 'a2', name: 'sub_agent' })]}
            onSelectAgent={vi.fn()}
        />);
        const rows = screen.getAllByTestId('spawn-card-row');
        expect(rows).toHaveLength(2);
        expect(screen.getByText('Coder')).toBeInTheDocument();
        expect(screen.getByText('Sub Agent')).toBeInTheDocument();
    });

    it('headers the card with the count and a status rollup', () => {
        render(<SpawnCard
            agents={[
                agent({ id: 'a1', status: 'running' }),
                agent({ id: 'a2', status: 'success' }),
                agent({ id: 'a3', status: 'error' }),
            ]}
            onSelectAgent={vi.fn()}
        />);
        const card = screen.getByTestId('spawn-card');
        expect(card).toHaveTextContent('spawn_agent · 3 agents');
        expect(card).toHaveTextContent('1 running · 1 done · 1 error');
    });

    it('shows iteration and context in the row meta', () => {
        render(<SpawnCard agents={[agent()]} onSelectAgent={vi.fn()} />);
        const row = screen.getByTestId('spawn-card-row');
        expect(row).toHaveTextContent('iter 3/12');
        expect(row).toHaveTextContent('4k / 32k');
    });

    it('calls onSelectAgent with the agent id when a row is clicked', async () => {
        const user = userEvent.setup();
        const onSelectAgent = vi.fn();
        render(<SpawnCard agents={[agent({ id: 'a9' })]} onSelectAgent={onSelectAgent} />);
        await user.click(screen.getByTestId('spawn-card-row'));
        expect(onSelectAgent).toHaveBeenCalledWith('a9');
    });
});
