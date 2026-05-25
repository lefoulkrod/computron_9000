import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ContextMeter from '../ContextMeter.jsx';

const usage = (used, limit, threshold = 0.75) => ({
    context_used: used,
    context_limit: limit,
    fill_ratio: used / limit,
    compaction_threshold: threshold,
});

describe('ContextMeter', () => {
    it('renders nothing without context usage', () => {
        const { container } = render(<ContextMeter contextUsage={null} />);
        expect(container).toBeEmptyDOMElement();
    });

    it('renders nothing when the context limit is missing', () => {
        const { container } = render(<ContextMeter contextUsage={{ context_used: 100, fill_ratio: 0.5 }} />);
        expect(container).toBeEmptyDOMElement();
    });

    it('formats token counts with k/M suffixes', () => {
        render(<ContextMeter contextUsage={usage(12847, 200000)} />);
        expect(screen.getByTestId('context-meter')).toHaveTextContent('13k');
        expect(screen.getByTestId('context-meter')).toHaveTextContent('/ 200k');
    });

    it('uses the low level well below the compaction threshold', () => {
        render(<ContextMeter contextUsage={usage(60000, 200000, 0.75)} />);
        expect(screen.getByTestId('context-meter')).toHaveAttribute('data-level', 'low');
    });

    it('uses the med level approaching the threshold', () => {
        // fill 0.65, threshold 0.75 → past 0.75*0.8=0.6, below 0.75
        render(<ContextMeter contextUsage={usage(130000, 200000, 0.75)} />);
        expect(screen.getByTestId('context-meter')).toHaveAttribute('data-level', 'med');
    });

    it('uses the high level at or above the threshold', () => {
        render(<ContextMeter contextUsage={usage(160000, 200000, 0.75)} />);
        expect(screen.getByTestId('context-meter')).toHaveAttribute('data-level', 'high');
    });

    it('shifts levels with the per-profile threshold', () => {
        // Same 55% fill reads differently against different thresholds.
        const { rerender } = render(<ContextMeter contextUsage={usage(110000, 200000, 0.5)} />);
        expect(screen.getByTestId('context-meter')).toHaveAttribute('data-level', 'high');
        rerender(<ContextMeter contextUsage={usage(110000, 200000, 0.9)} />);
        expect(screen.getByTestId('context-meter')).toHaveAttribute('data-level', 'low');
    });

    it('positions the tick at the compaction threshold', () => {
        render(<ContextMeter contextUsage={usage(50000, 200000, 0.6)} />);
        expect(screen.getByTestId('context-meter-tick')).toHaveStyle({ left: '60%' });
    });

    it('falls back to a 75% threshold when the field is absent', () => {
        render(<ContextMeter contextUsage={{ context_used: 160000, context_limit: 200000, fill_ratio: 0.8 }} />);
        // 0.8 fill, default 0.75 threshold → high
        expect(screen.getByTestId('context-meter')).toHaveAttribute('data-level', 'high');
        expect(screen.getByTestId('context-meter-tick')).toHaveStyle({ left: '75%' });
    });

    it('sets the fill width to the rounded fill percentage', () => {
        render(<ContextMeter contextUsage={usage(50000, 200000)} />);
        expect(screen.getByTestId('context-meter-fill')).toHaveStyle({ width: '25%' });
    });

    it('clamps the fill ratio to the 0-100% range', () => {
        render(<ContextMeter contextUsage={{ context_used: 220000, context_limit: 200000, fill_ratio: 1.1, compaction_threshold: 0.75 }} />);
        expect(screen.getByTestId('context-meter-fill')).toHaveStyle({ width: '100%' });
    });
});
