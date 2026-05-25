import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import ChatInput from '../ChatInput.jsx';

// Minimal 1x1 transparent PNG base64
const MOCK_BASE64_PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAADElEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg==';

describe('ChatInput', () => {
    it('renders textarea and buttons', () => {
        render(<ChatInput onSend={vi.fn()} isStreaming={false} />);

        expect(screen.getByPlaceholderText('Message Computron…')).toBeInTheDocument();
        expect(screen.getByLabelText('Attach file')).toBeInTheDocument();
        expect(screen.getByLabelText('Send message')).toBeInTheDocument();
    });

    it('calls onSend with message when submitted', async () => {
        const onSend = vi.fn();
        const user = userEvent.setup();
        render(<ChatInput onSend={onSend} isStreaming={false} />);

        const textarea = screen.getByPlaceholderText('Message Computron…');
        await user.type(textarea, 'Hello world');
        await user.click(screen.getByLabelText('Send message'));

        expect(onSend).toHaveBeenCalledWith('Hello world', null);
    });

    it('trims whitespace from messages', async () => {
        const onSend = vi.fn();
        const user = userEvent.setup();
        render(<ChatInput onSend={onSend} isStreaming={false} />);

        const textarea = screen.getByPlaceholderText('Message Computron…');
        await user.type(textarea, '  test message  ');
        await user.click(screen.getByLabelText('Send message'));

        expect(onSend).toHaveBeenCalledWith('test message', null);
    });

    it('clears message after sending', async () => {
        const onSend = vi.fn();
        const user = userEvent.setup();
        render(<ChatInput onSend={onSend} isStreaming={false} />);

        const textarea = screen.getByPlaceholderText('Message Computron…');
        await user.type(textarea, 'Hello');
        await user.click(screen.getByLabelText('Send message'));

        expect(textarea.value).toBe('');
    });

    it('submits on Enter key press', async () => {
        const onSend = vi.fn();
        const user = userEvent.setup();
        render(<ChatInput onSend={onSend} isStreaming={false} />);

        const textarea = screen.getByPlaceholderText('Message Computron…');
        await user.type(textarea, 'Test{Enter}');

        expect(onSend).toHaveBeenCalledWith('Test', null);
    });

    it('does not submit on Shift+Enter', async () => {
        const onSend = vi.fn();
        const user = userEvent.setup();
        render(<ChatInput onSend={onSend} isStreaming={false} />);

        const textarea = screen.getByPlaceholderText('Message Computron…');
        await user.type(textarea, 'Line 1{Shift>}{Enter}{/Shift}Line 2');

        expect(onSend).not.toHaveBeenCalled();
        expect(textarea.value).toContain('Line 1\nLine 2');
    });

    it('shows stop button and nudge placeholder when streaming', () => {
        render(<ChatInput onSend={vi.fn()} onStop={vi.fn()} isStreaming={true} />);

        expect(screen.getByLabelText('Stop generation')).toBeInTheDocument();
        expect(screen.getByPlaceholderText('Send a nudge…')).toBeInTheDocument();
        // While streaming the send button is replaced by stop.
        expect(screen.queryByLabelText('Send message')).not.toBeInTheDocument();
    });

    it('builds the placeholder from the selected profile name', async () => {
        const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue({
            json: () => Promise.resolve([{ id: 'p1', name: 'Code Expert' }]),
        });
        try {
            render(<ChatInput onSend={vi.fn()} isStreaming={false}
                selectedProfileId="p1" onProfileChange={vi.fn()} />);
            expect(await screen.findByPlaceholderText('Message Code Expert…')).toBeInTheDocument();
        } finally {
            fetchSpy.mockRestore();
        }
    });

    it('names the profile in the streaming nudge placeholder', async () => {
        const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue({
            json: () => Promise.resolve([{ id: 'p1', name: 'Code Expert' }]),
        });
        try {
            render(<ChatInput onSend={vi.fn()} onStop={vi.fn()} isStreaming={true}
                selectedProfileId="p1" onProfileChange={vi.fn()} />);
            expect(await screen.findByPlaceholderText('Send a nudge to Code Expert…')).toBeInTheDocument();
        } finally {
            fetchSpy.mockRestore();
        }
    });

    it('disables the send button when there is nothing to send', () => {
        render(<ChatInput onSend={vi.fn()} isStreaming={false} />);
        expect(screen.getByLabelText('Send message')).toBeDisabled();
    });

    it('renders a file card (not an image) for a non-image attachment', async () => {
        render(<ChatInput onSend={vi.fn()} isStreaming={false}
            attachment={{ base64: 'YWJj', contentType: 'application/pdf', filename: 'report.pdf' }} />);
        expect(await screen.findByText('report.pdf')).toBeInTheDocument();
        expect(screen.getByText(/^PDF/)).toBeInTheDocument();
        expect(screen.queryByTestId('attachment-image')).not.toBeInTheDocument();
    });

    it('handles file selection and displays preview', async () => {
        const onSend = vi.fn();
        const user = userEvent.setup();
        render(<ChatInput onSend={onSend} isStreaming={false} />);

        const file = new File(['dummy'], 'test.png', { type: 'image/png' });
        const fileInput = screen.getByLabelText('Attach file').closest('div').querySelector('input[type="file"]');

        await user.upload(fileInput, file);

        await waitFor(() => {
            expect(screen.getByTestId('attachment-image')).toBeInTheDocument();
        });
    });

    it('removes file attachment when remove button clicked', async () => {
        const onSend = vi.fn();
        const user = userEvent.setup();
        render(<ChatInput onSend={onSend} isStreaming={false} />);

        const file = new File(['dummy'], 'test.png', { type: 'image/png' });
        const fileInput = screen.getByLabelText('Attach file').closest('div').querySelector('input[type="file"]');

        await user.upload(fileInput, file);

        await waitFor(() => {
            expect(screen.getByTestId('attachment-image')).toBeInTheDocument();
        });

        const removeButton = screen.getByLabelText('Remove attachment');
        await user.click(removeButton);

        expect(screen.queryByTestId('attachment-image')).not.toBeInTheDocument();
    });

    it('sends file data with message', async () => {
        const onSend = vi.fn();
        const user = userEvent.setup();
        render(<ChatInput onSend={onSend} isStreaming={false} />);

        // Create a mock file
        const fileContent = MOCK_BASE64_PNG;
        const file = new File([atob(fileContent)], 'test.png', { type: 'image/png' });
        const fileInput = screen.getByLabelText('Attach file').closest('div').querySelector('input[type="file"]');

        await user.upload(fileInput, file);

        await waitFor(() => {
            expect(screen.getByTestId('attachment-image')).toBeInTheDocument();
        });

        const textarea = screen.getByPlaceholderText('Message Computron…');
        await user.type(textarea, 'Check this image');
        await user.click(screen.getByLabelText('Send message'));

        expect(onSend).toHaveBeenCalledWith(
            'Check this image',
            expect.objectContaining({
                content_type: 'image/png',
                base64: expect.any(String),
                filename: 'test.png',
            }),
        );
    });

    it('clears file after sending', async () => {
        const onSend = vi.fn();
        const user = userEvent.setup();
        render(<ChatInput onSend={onSend} isStreaming={false} />);

        const file = new File(['dummy'], 'test.png', { type: 'image/png' });
        const fileInput = screen.getByLabelText('Attach file').closest('div').querySelector('input[type="file"]');

        await user.upload(fileInput, file);

        await waitFor(() => {
            expect(screen.getByTestId('attachment-image')).toBeInTheDocument();
        });

        await user.click(screen.getByLabelText('Send message'));

        expect(screen.queryByTestId('attachment-image')).not.toBeInTheDocument();
    });

    describe('attachment prop', () => {
        it('sets attachment when attachment prop is provided', async () => {
            const onSend = vi.fn();
            const { rerender } = render(<ChatInput onSend={onSend} isStreaming={false} />);

            expect(screen.queryByTestId('attachment-image')).not.toBeInTheDocument();

            rerender(
                <ChatInput
                    onSend={onSend}
                    isStreaming={false}
                    attachment={{ base64: MOCK_BASE64_PNG, contentType: 'image/png' }}
                />
            );

            await waitFor(() => {
                expect(screen.getByTestId('attachment-image')).toBeInTheDocument();
            });
        });

        it('sends attached file with message', async () => {
            const onSend = vi.fn();
            const user = userEvent.setup();
            render(
                <ChatInput
                    onSend={onSend}
                    isStreaming={false}
                    attachment={{ base64: MOCK_BASE64_PNG, contentType: 'image/png' }}
                />
            );

            await waitFor(() => {
                expect(screen.getByTestId('attachment-image')).toBeInTheDocument();
            });

            const textarea = screen.getByPlaceholderText('Message Computron…');
            await user.type(textarea, 'External image');
            await user.click(screen.getByLabelText('Send message'));

            expect(onSend).toHaveBeenCalledWith(
                'External image',
                expect.objectContaining({
                    content_type: 'image/png',
                    base64: MOCK_BASE64_PNG,
                }),
            );
        });

        it('uses default contentType when not provided', async () => {
            const onSend = vi.fn();
            render(
                <ChatInput
                    onSend={onSend}
                    isStreaming={false}
                    attachment={{ base64: MOCK_BASE64_PNG }}
                />
            );

            await waitFor(() => {
                expect(screen.getByTestId('attachment-image')).toBeInTheDocument();
            });
        });

        it('can remove attached file', async () => {
            const onSend = vi.fn();
            const user = userEvent.setup();
            render(
                <ChatInput
                    onSend={onSend}
                    isStreaming={false}
                    attachment={{ base64: MOCK_BASE64_PNG, contentType: 'image/png' }}
                />
            );

            await waitFor(() => {
                expect(screen.getByTestId('attachment-image')).toBeInTheDocument();
            });

            const removeButton = screen.getByLabelText('Remove attachment');
            await user.click(removeButton);

            expect(screen.queryByTestId('attachment-image')).not.toBeInTheDocument();
        });
    });
});
