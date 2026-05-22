/**
 * Provider-step UI coverage for the setup wizard.
 *
 * Verifies the conditional-field visibility on step 1: which input
 * fields show up when each provider option is selected. (The wizard's
 * end-to-end flow is exercised by the autouse e2e fixture; these are
 * focused unit tests so the conditional logic stays covered without
 * needing wizard re-entry, which doesn't exist anymore.)
 */

import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';

import SetupWizard from '../SetupWizard.jsx';

function _mockFetch() {
    return vi.fn((url) => {
        if (url === '/api/integrations') {
            return Promise.resolve({ ok: true, json: () => Promise.resolve({ integrations: [] }) });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });
}

async function _advanceToProviderStep() {
    // Step 0 is the welcome; clicking "Get Started" advances to the provider step.
    fireEvent.click(screen.getByRole('button', { name: 'Get Started' }));
    await screen.findByText('Choose your LLM provider');
}

describe('SetupWizard provider-step field visibility', () => {
    beforeEach(() => {
        globalThis.fetch = _mockFetch();
    });

    it('shows only the Ollama URL field when Ollama is selected', async () => {
        const { container } = render(<SetupWizard onComplete={vi.fn()} />);
        await _advanceToProviderStep();

        await act(async () => {
            fireEvent.click(screen.getByText('Ollama (local)'));
        });

        expect(container.querySelector('#ollama-url')).toBeInTheDocument();
        expect(container.querySelector('#compat-url')).not.toBeInTheDocument();
        expect(container.querySelector('#compat-key')).not.toBeInTheDocument();
        expect(container.querySelector('#cloud-provider')).not.toBeInTheDocument();
        expect(container.querySelector('#cloud-key')).not.toBeInTheDocument();
    });

    it('shows the URL and optional API key when OpenAI-compatible is selected', async () => {
        const { container } = render(<SetupWizard onComplete={vi.fn()} />);
        await _advanceToProviderStep();

        await act(async () => {
            fireEvent.click(screen.getByText('OpenAI-compatible endpoint'));
        });

        expect(container.querySelector('#compat-url')).toBeInTheDocument();
        expect(container.querySelector('#compat-key')).toBeInTheDocument();
        expect(container.querySelector('#ollama-url')).not.toBeInTheDocument();
        expect(container.querySelector('#cloud-provider')).not.toBeInTheDocument();
        expect(container.querySelector('#cloud-key')).not.toBeInTheDocument();
    });

    it('shows the provider select and API key when Cloud API is selected', async () => {
        const { container } = render(<SetupWizard onComplete={vi.fn()} />);
        await _advanceToProviderStep();

        await act(async () => {
            fireEvent.click(screen.getByText('Cloud API'));
        });

        expect(container.querySelector('#cloud-provider')).toBeInTheDocument();
        expect(container.querySelector('#cloud-key')).toBeInTheDocument();
        expect(container.querySelector('#ollama-url')).not.toBeInTheDocument();
        expect(container.querySelector('#compat-url')).not.toBeInTheDocument();
        expect(container.querySelector('#compat-key')).not.toBeInTheDocument();
    });

    it('Cloud API offers Anthropic, OpenAI, and OpenRouter as choices', async () => {
        const { container } = render(<SetupWizard onComplete={vi.fn()} />);
        await _advanceToProviderStep();

        await act(async () => {
            fireEvent.click(screen.getByText('Cloud API'));
        });

        const select = container.querySelector('#cloud-provider');
        const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
        expect(values).toEqual(['anthropic', 'openai', 'openrouter']);
    });
});
