import { afterEach, describe, expect, it, vi } from 'vitest';
import copyToClipboard from '../copyToClipboard.js';

const originalClipboard = navigator.clipboard;
const originalExecCommand = document.execCommand;

afterEach(() => {
  if (originalClipboard === undefined) {
    delete navigator.clipboard;
  } else {
    navigator.clipboard = originalClipboard;
  }
  document.execCommand = originalExecCommand;
  document.body.innerHTML = '';
  vi.restoreAllMocks();
});

describe('copyToClipboard utility', () => {
  it('uses navigator clipboard API when available', async () => {
    const writeText = vi.fn().mockResolvedValue();
    navigator.clipboard = { writeText };
    document.execCommand = vi.fn();

    const result = await copyToClipboard('hello world');

    expect(result).toBe(true);
    expect(writeText).toHaveBeenCalledWith('hello world');
    expect(document.execCommand).not.toHaveBeenCalled();
  });

  it('falls back to execCommand when clipboard API is missing', async () => {
    delete navigator.clipboard;
    const execCommand = vi.fn().mockReturnValue(true);
    document.execCommand = execCommand;

    const result = await copyToClipboard('fallback text');

    expect(result).toBe(true);
    expect(execCommand).toHaveBeenCalledWith('copy');
  });

  it('returns false when both clipboard API and fallback fail', async () => {
    navigator.clipboard = {
      writeText: vi.fn().mockRejectedValue(new Error('no clipboard')),
    };
    document.execCommand = vi.fn(() => {
      throw new Error('exec failed');
    });

    const result = await copyToClipboard('fail');

    expect(result).toBe(false);
  });
});
