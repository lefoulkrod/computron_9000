import { useState } from 'react';
import MarkdownContent from './MarkdownContent.jsx';
import SpawnCard from './SpawnCard.jsx';
import FileOutput from './FileOutput.jsx';
import styles from './ActivityRail.module.css';

const _isSpawnRequested = (e) => e?.type === 'spawn_requested';

function _formatArgsPreview(args) {
    if (!args || typeof args !== 'object') return null;
    const pairs = Object.entries(args);
    if (pairs.length === 0) return null;
    const [firstKey, firstVal] = pairs[0];
    return { firstKey, firstVal, extra: pairs.length - 1, all: pairs };
}

function ToolCallRow({ name, args }) {
    const [open, setOpen] = useState(false);
    const preview = _formatArgsPreview(args);

    return (
        <>
            <div
                className={`${styles.tool}${open ? ` ${styles.toolOpen}` : ''}`}
                onClick={() => setOpen((v) => !v)}
                data-testid="activity-tool-call"
            >
                <span className={styles.chev} aria-hidden="true">▶</span>
                <span className={styles.toolBody}>
                    <span className={styles.toolName}>{name}</span>
                    <span className={styles.punct}>(</span>
                    {preview ? (
                        <>
                            <span className={styles.argInline}>
                                <span className={styles.argKey}>{preview.firstKey}=</span>
                                <span>{`"${preview.firstVal}"`}</span>
                            </span>
                            {preview.extra > 0 && (
                                <>
                                    <span className={styles.punct}>, </span>
                                    <span className={styles.more}>…</span>
                                </>
                            )}
                        </>
                    ) : null}
                    <span className={styles.punct}>)</span>
                </span>
            </div>
            {open && (
                <div className={styles.toolDetail} data-testid="activity-tool-detail">
                    <div className={styles.sectionLabel}>args</div>
                    {preview ? preview.all.map(([k, v]) => (
                        <div key={k} className={styles.pair}>
                            <span className={styles.pairKey}>{k}</span>
                            <span className={styles.pairValue}>{`"${v}"`}</span>
                        </div>
                    )) : (
                        <div className={styles.empty}>(no args)</div>
                    )}
                </div>
            )}
        </>
    );
}

function _renderRow(entry, idx, opts) {
    const { spawnedAgentsById, runIds, onSelectAgent, onPreview } = opts;

    if (entry.type === 'content') {
        return (
            <div key={idx} className={styles.row} data-testid="activity-row-content">
                <div className={styles.rail}>
                    <span className={`${styles.marker} ${styles.markerContent}`} aria-hidden="true" />
                </div>
                <div className={styles.main}>
                    <div className={styles.content} data-testid="entry-content">
                        <MarkdownContent>{entry.content}</MarkdownContent>
                    </div>
                </div>
            </div>
        );
    }

    if (entry.type === 'thinking') {
        return (
            <div key={idx} className={styles.row} data-testid="activity-row-thinking">
                <div className={styles.rail}>
                    <span className={styles.marker} aria-hidden="true" />
                </div>
                <div className={styles.main}>
                    <div className={styles.thinking}>
                        <MarkdownContent>{entry.thinking || ''}</MarkdownContent>
                    </div>
                </div>
            </div>
        );
    }

    if (entry.type === 'spawn_requested') {
        // First entry of a run renders the card; later entries drop out.
        if (idx > 0 && _isSpawnRequested(opts.entries[idx - 1])) return null;
        const ids = new Set();
        for (let j = idx; j < opts.entries.length && _isSpawnRequested(opts.entries[j]); j += 1) {
            if (opts.entries[j].correlationId) ids.add(opts.entries[j].correlationId);
        }
        const agents = [];
        for (const id of ids) {
            const a = spawnedAgentsById.get(id);
            if (a) agents.push(a);
        }
        if (agents.length === 0) return null;
        return (
            <div key={idx} className={styles.row} data-testid="activity-row-spawn">
                <div className={styles.rail}>
                    <span className={styles.marker} aria-hidden="true" />
                </div>
                <div className={styles.main}>
                    <SpawnCard agents={agents} onSelectAgent={onSelectAgent} />
                </div>
            </div>
        );
    }

    if (entry.type === 'tool_call') {
        // spawn_agent tool calls are surfaced as SpawnCards via the
        // matching spawn_requested entry — skip the raw tool row so
        // we don't render the same action twice.
        if (entry.name === 'spawn_agent') return null;
        // Group with the previous row if it was also a non-spawn tool_call
        // so consecutive tools share one rail marker visually.
        const prev = opts.entries[idx - 1];
        const groupStart = !prev || prev.type !== 'tool_call' || prev.name === 'spawn_agent';
        if (!groupStart) {
            return (
                <div key={idx} className={`${styles.row} ${styles.rowJoin}`} data-testid="activity-row-tool">
                    <div className={styles.rail} aria-hidden="true" />
                    <div className={styles.main}>
                        <ToolCallRow name={entry.name} args={entry.arguments} />
                    </div>
                </div>
            );
        }
        return (
            <div key={idx} className={styles.row} data-testid="activity-row-tool">
                <div className={styles.rail}>
                    <span className={styles.marker} aria-hidden="true" />
                </div>
                <div className={styles.main}>
                    <ToolCallRow name={entry.name} args={entry.arguments} />
                </div>
            </div>
        );
    }

    if (entry.type === 'file_output') {
        return (
            <div key={idx} className={styles.row} data-testid="activity-row-file">
                <div className={styles.rail}>
                    <span className={styles.marker} aria-hidden="true" />
                </div>
                <div className={styles.main}>
                    <FileOutput item={entry} onPreview={onPreview} />
                </div>
            </div>
        );
    }

    return null;
}

/**
 * Full-transcript renderer for the agent activity view. Every entry
 * sits on a continuous rail — content paragraphs are heaviest (the
 * outcome), thinking and tool calls share a lighter weight (process).
 * Tool calls collapse to a function-call signature with the first arg
 * shown; click expands the full key/value list.
 */
export default function ActivityRail({ entries, spawnedAgents, onSelectAgent, onPreview }) {
    if (!entries || entries.length === 0) return null;

    const spawnedAgentsById = new Map();
    for (const a of (spawnedAgents || [])) {
        if (a?.correlationId) spawnedAgentsById.set(a.correlationId, a);
    }

    return (
        <div className={styles.stream}>
            {entries.map((entry, i) => _renderRow(entry, i, {
                entries,
                spawnedAgentsById,
                onSelectAgent,
                onPreview,
            }))}
        </div>
    );
}
