import { describe, expect, it } from 'vitest';
import { _historyToMessages, _mergeFileOutputs } from '../useStreamingChat.js';

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

describe('_mergeFileOutputs', () => {
    function _turn(turnIdx, files) {
        const events = [
            { type: 'agent_started', agent_id: `root.computron.${turnIdx}`, parent_agent_id: null },
        ];
        for (const f of files) {
            events.push({ type: 'file_output', agent_id: `root.computron.${turnIdx}`, ...f });
        }
        events.push({ type: 'agent_completed', agent_id: `root.computron.${turnIdx}` });
        return events;
    }

    it('appends file_output entries to the assistant message for that turn', () => {
        const messages = _historyToMessages([
            { role: 'user', content: 'write a file' },
            { role: 'assistant', content: 'done' },
        ]);
        const events = _turn(1, [
            { filename: 'report.html', content_type: 'text/html', path: '/home/computron/report.html' },
        ]);
        _mergeFileOutputs(messages, events);

        const assistant = messages[1];
        const fileEntries = assistant.entries.filter((e) => e.type === 'file_output');
        expect(fileEntries).toHaveLength(1);
        expect(fileEntries[0].filename).toBe('report.html');
        expect(fileEntries[0].path).toBe('/home/computron/report.html');
    });

    it('routes files to the correct turn across multiple turns', () => {
        const messages = _historyToMessages([
            { role: 'user', content: 'first' },
            { role: 'assistant', content: 'one' },
            { role: 'user', content: 'second' },
            { role: 'assistant', content: 'two' },
        ]);
        const events = [
            ..._turn(1, [{ filename: 'a.html', content_type: 'text/html', path: '/p/a.html' }]),
            ..._turn(2, [{ filename: 'b.html', content_type: 'text/html', path: '/p/b.html' }]),
        ];
        _mergeFileOutputs(messages, events);

        const turn1Files = messages[1].entries.filter((e) => e.type === 'file_output');
        const turn2Files = messages[3].entries.filter((e) => e.type === 'file_output');
        expect(turn1Files.map((e) => e.filename)).toEqual(['a.html']);
        expect(turn2Files.map((e) => e.filename)).toEqual(['b.html']);
    });

    it('ignores sub-agent agent_started events when counting turns', () => {
        const messages = _historyToMessages([
            { role: 'user', content: 'go' },
            { role: 'assistant', content: 'done' },
        ]);
        const events = [
            { type: 'agent_started', agent_id: 'root.1', parent_agent_id: null },
            // sub-agent start should NOT advance turn counter
            { type: 'agent_started', agent_id: 'root.1.sub.2', parent_agent_id: 'root.1' },
            { type: 'file_output', agent_id: 'root.1.sub.2',
              filename: 'sub.txt', content_type: 'text/plain', path: '/p/sub.txt' },
            { type: 'file_output', agent_id: 'root.1',
              filename: 'root.txt', content_type: 'text/plain', path: '/p/root.txt' },
        ];
        _mergeFileOutputs(messages, events);

        const filenames = messages[1].entries
            .filter((e) => e.type === 'file_output')
            .map((e) => e.filename);
        // Both files land on the same turn; sub-agent vs root distinction
        // isn't surfaced in the chat view today.
        expect(filenames).toEqual(['sub.txt', 'root.txt']);
    });

    it('is a no-op when events is empty or missing', () => {
        const messages = _historyToMessages([
            { role: 'user', content: 'go' },
            { role: 'assistant', content: 'done' },
        ]);
        const before = messages[1].entries.length;
        _mergeFileOutputs(messages, []);
        _mergeFileOutputs(messages, null);
        _mergeFileOutputs(messages, undefined);
        expect(messages[1].entries).toHaveLength(before);
    });
});
