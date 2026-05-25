import CollapsibleThinking from './CollapsibleThinking.jsx';
import MarkdownContent from './MarkdownContent.jsx';
import ToolCallBlock from './ToolCallBlock.jsx';
import FileOutput from './FileOutput.jsx';
import SpawnCard from './SpawnCard.jsx';

/**
 * Pure renderer for an ordered list of agent entries: thinking blocks,
 * content text, tool calls, file outputs, spawn cards. Each entry's
 * `type` field picks the sub-component; the list renders in order.
 *
 * This component renders every entry it's given. Per-view filtering
 * (e.g. hiding thinking + tool_calls in the chat) belongs in the
 * caller — do NOT bake those rules in here, because one consumer (the
 * agent activity view) intentionally wants the full inline trace.
 */
const _isSpawnRequested = (e) => e?.type === 'spawn_requested';

export default function AgentOutput({ entries, streaming, showFileOutputs = true, onPreview, spawnedAgents, onSelectAgent }) {
    if (!entries || entries.length === 0) return null;

    // Each maximal run of consecutive spawn_requested entries becomes one
    // card. A response that spawns N agents in parallel emits N back-to-back
    // spawn_requested events, so one response = one card; later responses
    // with their own spawns get their own cards at their own positions.
    const agentsByCorrelation = new Map();
    for (const a of (spawnedAgents || [])) {
        if (a.correlationId) agentsByCorrelation.set(a.correlationId, a);
    }

    return entries.map((entry, i) => {
        if (entry.type === 'thinking') {
            return <CollapsibleThinking key={i} text={entry.thinking} streaming={streaming && i === entries.length - 1} />;
        }
        if (entry.type === 'content') {
            return <div key={i} data-testid="entry-content"><MarkdownContent streaming={streaming && i === entries.length - 1}>{entry.content}</MarkdownContent></div>;
        }
        if (entry.type === 'spawn_requested') {
            // Only the first entry of a run renders the card; later entries
            // in the same run drop out.
            if (i > 0 && _isSpawnRequested(entries[i - 1])) return null;
            const agents = [];
            for (let j = i; j < entries.length && _isSpawnRequested(entries[j]); j += 1) {
                const a = agentsByCorrelation.get(entries[j].correlationId);
                if (a) agents.push(a);
            }
            if (agents.length === 0) return null;
            return <SpawnCard key={i} agents={agents} onSelectAgent={onSelectAgent} />;
        }
        if (entry.type === 'tool_call') {
            return <ToolCallBlock key={i} name={entry.name} arguments={entry.arguments} />;
        }
        if (entry.type === 'file_output' && showFileOutputs) {
            return <FileOutput key={i} item={entry} onPreview={onPreview} />;
        }
        return null;
    });
}
