import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import Message from '../Message.jsx';

// Minimal 1x1 transparent PNG
const DATA_URL_PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAADElEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg==';
// Disallowed javascript URL disguised as image
const JS_URL = 'javascript:alert("x")';
// Simple (harmless) SVG turned into data URL
const DATA_URL_SVG = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxIiBoZWlnaHQ9IjEiPjxyZWN0IHdpZHRoPSIxIiBoZWlnaHQ9IjEiIGZpbGw9ImJsYWNrIi8+PC9zdmc+';

function renderAssistant(markdown) {
    return render(<Message role="assistant" content={markdown} />);
}

function renderUser(markdown) {
    return render(<Message role="user" content={markdown} />);
}

describe('Message markdown image handling', () => {
    it('renders data URL image in assistant message', () => {
        renderAssistant(`Here is an image: ![dot](${DATA_URL_PNG})`);
        const img = screen.getByRole('img', { name: /dot/i });
        expect(img).toBeInTheDocument();
        expect(img.getAttribute('src')).toBe(DATA_URL_PNG);
    });

    it('renders data URL image in user message', () => {
        renderUser(`User image: ![pixel](${DATA_URL_PNG})`);
        const img = screen.getByRole('img', { name: /pixel/i });
        expect(img).toBeInTheDocument();
        expect(img.getAttribute('src')).toBe(DATA_URL_PNG);
    });

    it('blocks javascript: image source', () => {
        renderAssistant(`Bad ref ![bad](${JS_URL})`);
        const img = screen.getByRole('img', { name: /bad/i });
        // urlTransform returns undefined so the src attribute is omitted
        expect(img.getAttribute('src')).toBe(null);
    });

    it('blocks svg data URL image', () => {
        renderAssistant(`Inline svg ![logo](${DATA_URL_SVG})`);
        const img = screen.getByRole('img', { name: /logo/i });
        expect(img.getAttribute('src')).toBe(null);
    });
});
