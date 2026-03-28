import { useRef, useEffect, useCallback, useState, useMemo } from 'react';
import AgentCard from './AgentCard.jsx';
import { useAgentState, useAgentDispatch } from '../hooks/useAgentState.jsx';
import styles from './AgentNetwork.module.css';

/**
 * Build individual trees for each root agent (BFS by level).
 * Returns an array of trees — each tree is an array of levels,
 * where each level is an array of agent **IDs** (not full objects).
 * This keeps the memo stable across data updates — fresh agent
 * objects are looked up at render time, not cached here.
 */
function _buildTrees(agents) {
    const rootIds = Object.keys(agents).filter((id) => agents[id].parentId === null);
    return rootIds
        // Only show trees that have sub-agents — single-agent turns
        // (root with no children) don't need a network visualization.
        .filter((id) => agents[id].childIds.length > 0)
        .map((rootId) => {
            const levels = [];
            let queue = [rootId];
            while (queue.length > 0) {
                const level = [];
                const nextQueue = [];
                for (const id of queue) {
                    const agent = agents[id];
                    if (!agent) continue;
                    level.push(id);
                    for (const childId of agent.childIds) {
                        nextQueue.push(childId);
                    }
                }
                if (level.length > 0) levels.push(level);
                queue = nextQueue;
            }
            return levels;
        });
}

/**
 * Draw SVG bezier connectors between parent and child cards.
 * Uses actual rendered DOM positions (getBoundingClientRect) so
 * connectors stay accurate as cards resize or the window changes.
 * Called on topology changes and ResizeObserver ticks.
 */
function _drawConnectors(containerEl, svgEl, agents) {
    if (!containerEl || !svgEl) return;
    const cr = containerEl.getBoundingClientRect();
    svgEl.setAttribute('viewBox', `0 0 ${cr.width} ${cr.height}`);
    svgEl.style.width = cr.width + 'px';
    svgEl.style.height = cr.height + 'px';

    let paths = '';
    for (const agent of Object.values(agents)) {
        if (!agent.parentId) continue;
        const parentEl = containerEl.querySelector(`[data-agent-id="${agent.parentId}"]`);
        const childEl = containerEl.querySelector(`[data-agent-id="${agent.id}"]`);
        if (!parentEl || !childEl) continue;

        const pr = parentEl.getBoundingClientRect();
        const chr = childEl.getBoundingClientRect();
        const fx = pr.left - cr.left + pr.width / 2;
        const fy = pr.top - cr.top + pr.height;
        const tx = chr.left - cr.left + chr.width / 2;
        const ty = chr.top - cr.top;
        const my = (fy + ty) / 2;

        paths += `<path d="M ${fx},${fy} C ${fx},${my} ${tx},${my} ${tx},${ty}" stroke="#3a3a4c" stroke-width="1.5" fill="none"/>`;
    }
    svgEl.innerHTML = paths;
}

/**
 * Shows all agents as a tree of cards with lines connecting parents
 * to children. Click a card to see its full activity.
 *
 * The tree layout and line drawing only recalculate when agents are
 * added/removed. A 1-second timer updates elapsed times on running cards.
 */
export default function AgentNetwork() {
    const { agents } = useAgentState();
    const dispatch = useAgentDispatch();
    const containerRef = useRef(null);
    const svgRef = useRef(null);
    const [tick, setTick] = useState(0);

    const handleSelect = useCallback((agentId) => {
        dispatch({ type: 'SELECT_AGENT', agentId });
    }, [dispatch]);

    // Only changes when agents are added/removed (not on every status update)
    const topoKey = useMemo(() => {
        return Object.values(agents)
            .map((a) => `${a.id}:${a.parentId || ''}`)
            .sort()
            .join('|');
    }, [agents]);

    // Redraw connectors only on topology or resize changes
    useEffect(() => {
        if (!containerRef.current || !svgRef.current) return;
        _drawConnectors(containerRef.current, svgRef.current, agents);
    }, [topoKey, tick]); // eslint-disable-line react-hooks/exhaustive-deps

    // Observe resize to redraw connectors
    useEffect(() => {
        if (!containerRef.current) return;
        const observer = new ResizeObserver(() => setTick((t) => t + 1));
        observer.observe(containerRef.current);
        return () => observer.disconnect();
    }, []);

    // Build per-root trees for layout (memoized on topology)
    const trees = useMemo(() => _buildTrees(agents), [topoKey]); // eslint-disable-line react-hooks/exhaustive-deps
    // Count only agents visible in the rendered trees (not childless roots
    // from past turns, which are filtered out of the graph).
    const { agentCount, runningCount, completeCount, errorCount } = useMemo(() => {
        const visibleIds = new Set(trees.flat(2));
        let running = 0, complete = 0, error = 0;
        for (const id of visibleIds) {
            const a = agents[id];
            if (!a) continue;
            if (a.status === 'running') running++;
            else if (a.status === 'success') complete++;
            else if (a.status === 'error') error++;
        }
        return { agentCount: visibleIds.size, runningCount: running, completeCount: complete, errorCount: error };
    }, [trees, agents]);

    // Update elapsed time every second for running agents
    useEffect(() => {
        if (runningCount === 0) return;
        const id = setInterval(() => setTick((t) => t + 1), 1000);
        return () => clearInterval(id);
    }, [runningCount]);

    return (
        <div className={styles.container}>
            <div className={styles.header}>
                <h2 className={styles.title}>Agent Network</h2>
                <span className={styles.count}>{agentCount} agent{agentCount !== 1 ? 's' : ''}</span>
                <div className={styles.legend}>
                    {runningCount > 0 && (
                        <span className={styles.legendItem}>
                            <span className={`${styles.legendDot} ${styles.running}`} />
                            running
                        </span>
                    )}
                    {completeCount > 0 && (
                        <span className={styles.legendItem}>
                            <span className={`${styles.legendDot} ${styles.success}`} />
                            complete
                        </span>
                    )}
                    {errorCount > 0 && (
                        <span className={styles.legendItem}>
                            <span className={`${styles.legendDot} ${styles.error}`} />
                            error
                        </span>
                    )}
                </div>
            </div>
            <div className={styles.graphArea} ref={containerRef}>
                <svg className={styles.connectors} ref={svgRef} />
                <div className={styles.forest}>
                    {trees.map((tree, treeIdx) => (
                        <div key={treeIdx} className={styles.tree}>
                            {tree.map((level, depth) => (
                                <div key={depth} className={styles.level}>
                                    {level.map((agentId) => (
                                        <div key={agentId} data-agent-id={agentId} className={styles.nodeWrap}>
                                            <AgentCard agent={agents[agentId]} onClick={handleSelect} />
                                        </div>
                                    ))}
                                </div>
                            ))}
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
