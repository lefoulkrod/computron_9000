import React, { useRef, useEffect, useCallback, useState } from 'react';
import AgentCard from './AgentCard.jsx';
import { useAgentState, useAgentDispatch } from '../hooks/useAgentState.jsx';
import styles from './AgentNetwork.module.css';

/**
 * Build individual trees for each root agent.
 * Returns an array of trees, where each tree is an array of levels.
 */
function _buildTrees(agents) {
    const rootIds = Object.keys(agents).filter((id) => agents[id].parentId === null);
    return rootIds.map((rootId) => {
        const levels = [];
        let queue = [rootId];
        while (queue.length > 0) {
            const level = [];
            const nextQueue = [];
            for (const id of queue) {
                const agent = agents[id];
                if (!agent) continue;
                level.push(agent);
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

export default function AgentNetwork() {
    const { agents } = useAgentState();
    const dispatch = useAgentDispatch();
    const containerRef = useRef(null);
    const svgRef = useRef(null);
    const [tick, setTick] = useState(0);

    const handleSelect = useCallback((agentId) => {
        dispatch({ type: 'SELECT_AGENT', agentId });
    }, [dispatch]);

    // Redraw connectors on layout changes
    useEffect(() => {
        if (!containerRef.current || !svgRef.current) return;
        _drawConnectors(containerRef.current, svgRef.current, agents);
    }, [agents, tick]);

    // Observe resize to redraw connectors
    useEffect(() => {
        if (!containerRef.current) return;
        const observer = new ResizeObserver(() => setTick((t) => t + 1));
        observer.observe(containerRef.current);
        return () => observer.disconnect();
    }, []);

    // Build per-root trees for layout
    const trees = _buildTrees(agents);
    const agentList = Object.values(agents);
    let runningCount = 0, completeCount = 0, errorCount = 0;
    for (const a of agentList) {
        if (a.status === 'running') runningCount++;
        else if (a.status === 'success') completeCount++;
        else if (a.status === 'error') errorCount++;
    }
    const agentCount = agentList.length;

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
                                    {level.map((agent) => (
                                        <div key={agent.id} data-agent-id={agent.id} className={styles.nodeWrap}>
                                            <AgentCard agent={agent} onClick={handleSelect} />
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
