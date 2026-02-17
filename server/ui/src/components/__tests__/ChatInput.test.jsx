import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import ChatInput from '../ChatInput.jsx';

// Minimal 1x1 transparent PNG base64
const MOCK_BASE64_PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAADElEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg==';

describe('ChatInput', () => {
    it('renders textarea and buttons', () => {
        render(<ChatInput onSend={vi.fn()} disabled={false} />);

        expect(screen.getByPlaceholderText('Type your message...')).toBeInTheDocument();
        expect(screen.getByLabelText('Attach file')).toBeInTheDocument();
        expect(screen.getByLabelText('Send message')).toBeInTheDocument();
    });

    it('calls onSend with message when submitted', async () => {
        const onSend = vi.fn();
        const user = userEvent.setup();
        render(<ChatInput onSend={onSend} disabled={false} />);

        const textarea = screen.getByPlaceholderText('Type your message...');
        await user.type(textarea, 'Hello world');
        await user.click(screen.getByLabelText('Send message'));

        expect(onSend).toHaveBeenCalledWith('Hello world', null);
    });

    it('trims whitespace from messages', async () => {
        const onSend = vi.fn();
        const user = userEvent.setup();
        render(<ChatInput onSend={onSend} disabled={false} />);

        const textarea = screen.getByPlaceholderText('Type your message...');
        await user.type(textarea, '  test message  ');
        await user.click(screen.getByLabelText('Send message'));

        expect(onSend).toHaveBeenCalledWith('test message', null);
    });

    it('clears message after sending', async () => {
        const onSend = vi.fn();
        const user = userEvent.setup();
        render(<ChatInput onSend={onSend} disabled={false} />);

        const textarea = screen.getByPlaceholderText('Type your message...');
        await user.type(textarea, 'Hello');
        await user.click(screen.getByLabelText('Send message'));

        expect(textarea.value).toBe('');
    });

    it('submits on Enter key press', async () => {
        const onSend = vi.fn();
        const user = userEvent.setup();
        render(<ChatInput onSend={onSend} disabled={false} />);

        const textarea = screen.getByPlaceholderText('Type your message...');
        await user.type(textarea, 'Test{Enter}');

        expect(onSend).toHaveBeenCalledWith('Test', null);
    });

    it('does not submit on Shift+Enter', async () => {
        const onSend = vi.fn();
        const user = userEvent.setup();
        render(<ChatInput onSend={onSend} disabled={false} />);

        const textarea = screen.getByPlaceholderText('Type your message...');
        await user.type(textarea, 'Line 1{Shift>}{Enter}{/Shift}Line 2');

        expect(onSend).not.toHaveBeenCalled();
        expect(textarea.value).toContain('Line 1\nLine 2');
    });

    it('does not submit when disabled', async () => {
        const onSend = vi.fn();
        const user = userEvent.setup();
        render(<ChatInput onSend={onSend} disabled={true} />);

        const textarea = screen.getByPlaceholderText('Type your message...');
        const sendButton = screen.getByLabelText('Send message');

        expect(textarea).toBeDisabled();
        expect(sendButton).toBeDisabled();

        await user.type(textarea, 'Test');
        await user.click(sendButton);

        expect(onSend).not.toHaveBeenCalled();
    });

    it('handles file selection and displays preview', async () => {
        const onSend = vi.fn();
        const user = userEvent.setup();
        render(<ChatInput onSend={onSend} disabled={false} />);

        const file = new File(['dummy'], 'test.png', { type: 'image/png' });
        const fileInput = screen.getByLabelText('Attach file').closest('div').querySelector('input[type="file"]');

        await user.upload(fileInput, file);

        await waitFor(() => {
            expect(screen.getByAltText('selected')).toBeInTheDocument();
        });
    });

    it('removes file attachment when remove button clicked', async () => {
        const onSend = vi.fn();
        const user = userEvent.setup();
        render(<ChatInput onSend={onSend} disabled={false} />);

        const file = new File(['dummy'], 'test.png', { type: 'image/png' });
        const fileInput = screen.getByLabelText('Attach file').closest('div').querySelector('input[type="file"]');

        await user.upload(fileInput, file);

        await waitFor(() => {
            expect(screen.getByAltText('selected')).toBeInTheDocument();
        });

        const removeButton = screen.getByLabelText('Remove image');
        await user.click(removeButton);

        expect(screen.queryByAltText('selected')).not.toBeInTheDocument();
    });

    it('sends file data with message', async () => {
        const onSend = vi.fn();
        const user = userEvent.setup();
        render(<ChatInput onSend={onSend} disabled={false} />);

        // Create a mock file
        const fileContent = MOCK_BASE64_PNG;
        const file = new File([atob(fileContent)], 'test.png', { type: 'image/png' });
        const fileInput = screen.getByLabelText('Attach file').closest('div').querySelector('input[type="file"]');

        await user.upload(fileInput, file);

        await waitFor(() => {
            expect(screen.getByAltText('selected')).toBeInTheDocument();
        });

        const textarea = screen.getByPlaceholderText('Type your message...');
        await user.type(textarea, 'Check this image');
        await user.click(screen.getByLabelText('Send message'));

        expect(onSend).toHaveBeenCalledWith(
            'Check this image',
            expect.objectContaining({
                content_type: 'image/png',
                base64: expect.any(String)
            })
        );
    });

    it('clears file after sending', async () => {
        const onSend = vi.fn();
        const user = userEvent.setup();
        render(<ChatInput onSend={onSend} disabled={false} />);

        const file = new File(['dummy'], 'test.png', { type: 'image/png' });
        const fileInput = screen.getByLabelText('Attach file').closest('div').querySelector('input[type="file"]');

        await user.upload(fileInput, file);

        await waitFor(() => {
            expect(screen.getByAltText('selected')).toBeInTheDocument();
        });

        await user.click(screen.getByLabelText('Send message'));

        expect(screen.queryByAltText('selected')).not.toBeInTheDocument();
    });

    describe('attachment prop', () => {
        it('sets attachment when attachment prop is provided', async () => {
            const onSend = vi.fn();
            const { rerender } = render(<ChatInput onSend={onSend} disabled={false} />);

            expect(screen.queryByAltText('selected')).not.toBeInTheDocument();

            rerender(
                <ChatInput
                    onSend={onSend}
                    disabled={false}
                    attachment={{ base64: MOCK_BASE64_PNG, contentType: 'image/png' }}
                />
            );

            await waitFor(() => {
                expect(screen.getByAltText('selected')).toBeInTheDocument();
            });
        });

        it('sends attached file with message', async () => {
            const onSend = vi.fn();
            const user = userEvent.setup();
            render(
                <ChatInput
                    onSend={onSend}
                    disabled={false}
                    attachment={{ base64: MOCK_BASE64_PNG, contentType: 'image/png' }}
                />
            );

            await waitFor(() => {
                expect(screen.getByAltText('selected')).toBeInTheDocument();
            });

            const textarea = screen.getByPlaceholderText('Type your message...');
            await user.type(textarea, 'External image');
            await user.click(screen.getByLabelText('Send message'));

            expect(onSend).toHaveBeenCalledWith(
                'External image',
                expect.objectContaining({
                    content_type: 'image/png',
                    base64: MOCK_BASE64_PNG
                })
            );
        });

        it('uses default contentType when not provided', async () => {
            const onSend = vi.fn();
            render(
                <ChatInput
                    onSend={onSend}
                    disabled={false}
                    attachment={{ base64: MOCK_BASE64_PNG }}
                />
            );

            await waitFor(() => {
                expect(screen.getByAltText('selected')).toBeInTheDocument();
            });
        });

        it('can remove attached file', async () => {
            const onSend = vi.fn();
            const user = userEvent.setup();
            render(
                <ChatInput
                    onSend={onSend}
                    disabled={false}
                    attachment={{ base64: MOCK_BASE64_PNG, contentType: 'image/png' }}
                />
            );

            await waitFor(() => {
                expect(screen.getByAltText('selected')).toBeInTheDocument();
            });

            const removeButton = screen.getByLabelText('Remove image');
            await user.click(removeButton);

            expect(screen.queryByAltText('selected')).not.toBeInTheDocument();
        });
    });
});
