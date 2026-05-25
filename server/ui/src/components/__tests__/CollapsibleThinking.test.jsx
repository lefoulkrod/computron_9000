import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import CollapsibleThinking from '../CollapsibleThinking.jsx';

describe('CollapsibleThinking', () => {
    it('renders nothing without text', () => {
        const { container } = render(<CollapsibleThinking text="" />);
        expect(container).toBeEmptyDOMElement();
    });

    it('starts expanded while streaming', () => {
        render(<CollapsibleThinking text="weighing options" streaming />);
        expect(screen.getByText('Thinking…')).toBeInTheDocument();
        expect(screen.getByText('weighing options')).toBeInTheDocument();
    });

    it('starts collapsed for a finished block', () => {
        render(<CollapsibleThinking text="weighing options" streaming={false} />);
        expect(screen.getByText('Show thinking')).toBeInTheDocument();
        expect(screen.queryByText('weighing options')).not.toBeInTheDocument();
    });

    it('auto-collapses when streaming ends', () => {
        const { rerender } = render(<CollapsibleThinking text="weighing options" streaming />);
        expect(screen.getByText('weighing options')).toBeInTheDocument();

        rerender(<CollapsibleThinking text="weighing options" streaming={false} />);
        expect(screen.queryByText('weighing options')).not.toBeInTheDocument();
        expect(screen.getByText('Show thinking')).toBeInTheDocument();
    });

    it('expands a finished block when the header is clicked', async () => {
        const user = userEvent.setup();
        render(<CollapsibleThinking text="weighing options" streaming={false} />);

        await user.click(screen.getByTestId('thinking-toggle'));
        expect(screen.getByText('weighing options')).toBeInTheDocument();
        expect(screen.getByText('Hide thinking')).toBeInTheDocument();
    });

    it('keeps the reader’s choice — no auto-collapse after a manual toggle', async () => {
        const user = userEvent.setup();
        const { rerender } = render(<CollapsibleThinking text="weighing options" streaming />);

        // Reader collapses mid-stream, then re-expands — they are now in control.
        await user.click(screen.getByTestId('thinking-toggle'));
        await user.click(screen.getByTestId('thinking-toggle'));
        expect(screen.getByText('weighing options')).toBeInTheDocument();

        // Streaming ends — the block stays expanded because the reader touched it.
        rerender(<CollapsibleThinking text="weighing options" streaming={false} />);
        expect(screen.getByText('weighing options')).toBeInTheDocument();
    });
});
