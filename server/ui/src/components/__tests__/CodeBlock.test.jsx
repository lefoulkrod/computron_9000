import { act } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PreCodeBlock } from '../CodeBlock.jsx';

vi.mock('../../utils/copyToClipboard.js', () => {
  const mockFn = vi.fn();
  return {
    __esModule: true,
    default: mockFn,
    copyToClipboard: mockFn,
  };
});

import copyToClipboard from '../../utils/copyToClipboard.js';

const CODE_SAMPLE = 'const answer = 42;\nconsole.log(answer);';

const renderCopyBlock = () =>
  render(
    <PreCodeBlock>
      <code className="language-javascript">{CODE_SAMPLE}</code>
    </PreCodeBlock>
  );

describe('PreCodeBlock copy button', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('copies code when clipboard helper resolves', async () => {
    copyToClipboard.mockResolvedValue(true);
    const user = userEvent.setup();
    renderCopyBlock();

    const button = screen.getByRole('button', { name: /copy code/i });
    await act(async () => {
      await user.click(button);
    });

    expect(copyToClipboard).toHaveBeenCalledWith(CODE_SAMPLE);
    expect(await screen.findByText(/copied!/i)).toBeInTheDocument();

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 2100));
    });
  });

  it('does not flip UI state when copy helper fails', async () => {
    copyToClipboard.mockResolvedValue(false);
    const user = userEvent.setup();
    renderCopyBlock();

    const button = screen.getByRole('button', { name: /copy code/i });
    await act(async () => {
      await user.click(button);
    });

    expect(copyToClipboard).toHaveBeenCalledWith(CODE_SAMPLE);
    expect(screen.getByRole('button', { name: /copy code/i })).toBeInTheDocument();
    expect(screen.queryByText(/copied!/i)).not.toBeInTheDocument();
  });
});
