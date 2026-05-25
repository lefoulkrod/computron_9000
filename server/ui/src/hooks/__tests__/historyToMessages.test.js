import { describe, expect, it } from 'vitest';
import { _historyToMessages } from '../useStreamingChat.js';

describe('_historyToMessages', () => {
    it('merges consecutive assistant round-trips into one message', () => {
        const out = _historyToMessages([
            { role: 'user', content: 'go' },
            { role: 'assistant', thinking: 't1', tool_calls: [{ function: { name: 'read_file' } }] },
            { role: 'tool', content: 'file contents' },
            { role: 'assistant', content: 'done', tool_calls: [{ function: { name: 'edit_file' } }] },
            { role: 'tool', content: 'ok' },
            { role: 'assistant', content: 'final answer' },
        ]);

        expect(out).toHaveLength(2); // one user, one merged assistant
        expect(out[0].role).toBe('user');
        const assistant = out[1];
        expect(assistant.role).toBe('assistant');
        // thinking + tool_call + content + tool_call + content, in order
        expect(assistant.entries.map((e) => e.type)).toEqual([
            'thinking', 'tool_call', 'content', 'tool_call', 'content',
        ]);
    });

    it('starts a fresh assistant message after each user message', () => {
        const out = _historyToMessages([
            { role: 'user', content: 'first' },
            { role: 'assistant', content: 'reply one' },
            { role: 'user', content: 'second' },
            { role: 'assistant', content: 'reply two' },
        ]);
        expect(out.map((m) => m.role)).toEqual(['user', 'assistant', 'user', 'assistant']);
        expect(out[1].entries).toHaveLength(1);
        expect(out[3].entries).toHaveLength(1);
    });

    it('skips system and tool messages', () => {
        const out = _historyToMessages([
            { role: 'system', content: 'sys' },
            { role: 'user', content: 'hi' },
            { role: 'tool', content: 'tool output' },
        ]);
        expect(out.map((m) => m.role)).toEqual(['user']);
    });

    it('drops assistant messages with no displayable entries', () => {
        const out = _historyToMessages([
            { role: 'user', content: 'hi' },
            { role: 'assistant', content: '' },
        ]);
        expect(out.map((m) => m.role)).toEqual(['user']);
    });

    it('whitespace-collapses and caps tool-call arguments from history', () => {
        const longArg = JSON.stringify({ content: `line one\n\n${'x'.repeat(200)}` });
        const out = _historyToMessages([
            { role: 'user', content: 'go' },
            { role: 'assistant', tool_calls: [{ function: { name: 'write_file', arguments: longArg } }] },
        ]);
        const value = out[1].entries[0].arguments.content;
        expect(value).not.toContain('\n');
        expect(value.length).toBe(64);
        expect(value.endsWith('…')).toBe(true);
    });
});
