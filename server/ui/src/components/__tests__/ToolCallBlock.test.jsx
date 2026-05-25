import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ToolCallBlock from '../ToolCallBlock.jsx';

describe('ToolCallBlock', () => {
    it('renders the tool name', () => {
        render(<ToolCallBlock name="read_file" />);
        expect(screen.getByText('read_file')).toBeInTheDocument();
    });

    it('renders no argument list when there are no arguments', () => {
        render(<ToolCallBlock name="read_file" />);
        expect(screen.queryByTestId('tool-call-args')).not.toBeInTheDocument();
    });

    it('renders arguments as named function-call kwargs', () => {
        render(<ToolCallBlock name="grep" arguments={{ pattern: 'flushPartial', path: 'src/' }} />);
        const args = screen.getByTestId('tool-call-args');
        expect(args).toHaveTextContent('pattern=');
        expect(args).toHaveTextContent('"flushPartial"');
        expect(args).toHaveTextContent('path=');
        expect(args).toHaveTextContent('"src/"');
    });

    it('ignores an empty arguments object', () => {
        render(<ToolCallBlock name="read_file" arguments={{}} />);
        expect(screen.queryByTestId('tool-call-args')).not.toBeInTheDocument();
    });

    it('renders argument values verbatim (capping happens upstream)', () => {
        render(<ToolCallBlock name="read_file" arguments={{ filename: 'src/app.py' }} />);
        expect(screen.getByTestId('tool-call-args')).toHaveTextContent('filename="src/app.py"');
    });
});
