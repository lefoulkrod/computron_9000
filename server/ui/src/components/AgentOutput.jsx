import CollapsibleThinking from './CollapsibleThinking.jsx';
import MarkdownContent from './MarkdownContent.jsx';
import ToolCallBlock from './ToolCallBlock.jsx';
import FileOutput from './FileOutput.jsx';

/**
 * Renders agent output as an ordered list of entries: thinking blocks,
 * content text, tool calls, and file outputs. Used by both the chat
 * view (Message.jsx) and the agent activity view (AgentActivityView.jsx).
 *
 * Each entry has a `type` field that determines how it renders.
 * Entries are displayed in chronological order — the same order
 * they were emitted by the agent.
 */
export default function AgentOutput({ entries, streaming, showFileOutputs = true, onPreview }) {
    if (!entries || entries.length === 0) return null;

    return entries.map((entry, i) => {
        if (entry.type === 'thinking') {
            return <CollapsibleThinking key={i} text={entry.thinking} streaming={streaming && i === entries.length - 1} />;
        }
        if (entry.type === 'content') {
            return <MarkdownContent key={i} streaming={streaming && i === entries.length - 1}>{entry.content}</MarkdownContent>;
        }
        if (entry.type === 'tool_call') {
            return <ToolCallBlock key={i} name={entry.name} />;
        }
        if (entry.type === 'file_output' && showFileOutputs) {
            return <FileOutput key={i} item={entry} onPreview={onPreview} />;
        }
        return null;
    });
}
