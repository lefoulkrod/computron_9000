import { useState, useEffect, useRef, useMemo } from 'react';
import RunDetail from './RunDetail.jsx';
import TaskDetail from './TaskDetail.jsx';
import { StatusIcon, formatTime, formatDuration, formatCron } from './goalUtils.jsx';
import styles from './GoalView.module.css';

export default function GoalView({ goal, onBack, onDeleteGoal, onDeleteRun, onPauseGoal, onResumeGoal, onTriggerGoal, fetchDetail }) {
    const [detail, setDetail] = useState(null);
    const [tab, setTab] = useState('tasks');
    const [selectedRunId, setSelectedRunId] = useState(null);
    const [selectedTaskId, setSelectedTaskId] = useState(null);
    const lastDetailJson = useRef('');
    const selectedRunRef = useRef(selectedRunId);
    const selectedTaskRef = useRef(selectedTaskId);
    selectedRunRef.current = selectedRunId;
    selectedTaskRef.current = selectedTaskId;

    useEffect(() => {
        let active = true;
        const load = async () => {
            const data = await fetchDetail();
            if (!active) return;
            const json = JSON.stringify(data);
            if (json !== lastDetailJson.current) {
                lastDetailJson.current = json;
                setDetail(data);
            }
            if (data.runs?.length && !selectedRunRef.current) {
                setSelectedRunId(data.runs[data.runs.length - 1].id);
            }
            if (data.tasks?.length && !selectedTaskRef.current) {
                setSelectedTaskId(data.tasks[0].id);
            }
        };
        load();
        const id = setInterval(load, 5000);
        return () => { active = false; clearInterval(id); };
    }, [goal.id]); // eslint-disable-line react-hooks/exhaustive-deps

    // Clear stale selectedRunId when the selected run disappears from polled data
    const runIds = detail?.runs?.map(r => r.id);
    const validSelectedRunId = runIds && selectedRunId && !runIds.includes(selectedRunId) ? null : selectedRunId;
    if (validSelectedRunId !== selectedRunId) setSelectedRunId(validSelectedRunId);

    const selectedRun = detail?.runs?.find(r => r.id === validSelectedRunId);
    const selectedTask = detail?.tasks?.find(t => t.id === selectedTaskId);
    const isActive = goal.status === 'active';

    const taskMap = useMemo(
        () => Object.fromEntries((detail?.tasks || []).map(t => [t.id, t])),
        [detail?.tasks],
    );

    return (
        <div className={styles.container}>
            {/* Header */}
            <div className={styles.header}>
                <div className={styles.backRow}>
                    <button className={styles.backBtn} onClick={onBack}>&larr; Goals</button>
                </div>
                <div className={styles.titleRow}>
                    <StatusIcon status={goal.status} size={12} />
                    <span className={styles.title}>{goal.description}</span>
                    {goal.cron && (
                        <span className={styles.cronBadge}>
                            {formatCron(goal.cron)}
                            {goal.timezone && <span className={styles.tzSuffix}>{goal.timezone}</span>}
                        </span>
                    )}
                    <div className={styles.actions}>
                        <button className={styles.actionBtn} onClick={() => onTriggerGoal(goal.id)}>Run Now</button>
                        {isActive ? (
                            <button className={styles.actionBtn} onClick={() => onPauseGoal(goal.id)}>Pause</button>
                        ) : (
                            <button className={styles.actionBtn} onClick={() => onResumeGoal(goal.id)}>Resume</button>
                        )}
                        <button className={`${styles.actionBtn} ${styles.danger}`} onClick={() => { onDeleteGoal(goal.id); onBack(); }}>
                            Delete
                        </button>
                    </div>
                </div>
            </div>

            <div className={styles.body}>
                {/* Left pane with tabs */}
                <div className={styles.leftPane}>
                    <div className={styles.tabBar}>
                        <button
                            className={`${styles.tab} ${tab === 'runs' ? styles.tabActive : ''}`}
                            onClick={() => setTab('runs')}
                        >Runs</button>
                        <button
                            className={`${styles.tab} ${tab === 'tasks' ? styles.tabActive : ''}`}
                            onClick={() => setTab('tasks')}
                        >Tasks</button>
                    </div>

                    <div className={styles.tabContent}>
                        {tab === 'runs' && (
                            <>
                                {detail?.runs?.slice().reverse().map(run => (
                                    <div
                                        key={run.id}
                                        className={`${styles.runItem} ${run.id === validSelectedRunId ? styles.selected : ''}`}
                                        onClick={() => setSelectedRunId(run.id)}
                                    >
                                        <StatusIcon status={run.status} />
                                        <div className={styles.runInfo}>
                                            <div className={styles.runLabel}>Run #{run.run_number}</div>
                                            <div className={styles.runTime}>
                                                {formatTime(run.created_at)}
                                                {run.status === 'running' ? ' \u00B7 running' : ''}
                                                {run.completed_at ? ` \u00B7 ${formatDuration(run.started_at, run.completed_at)}` : ''}
                                                {run.status === 'failed' ? ' \u00B7 failed' : ''}
                                            </div>
                                        </div>
                                        <button
                                            className={styles.deleteRunBtn}
                                            title="Delete run"
                                            onClick={e => { e.stopPropagation(); onDeleteRun(run.id); }}
                                        >&times;</button>
                                    </div>
                                ))}
                                {(!detail?.runs || detail.runs.length === 0) && (
                                    <div className={styles.emptyMsg}>No runs yet</div>
                                )}
                            </>
                        )}

                        {tab === 'tasks' && (
                            <>
                                {detail?.tasks?.map((task, i) => (
                                    <div
                                        key={task.id}
                                        className={`${styles.taskDefItem} ${task.id === selectedTaskId ? styles.selected : ''}`}
                                        onClick={() => setSelectedTaskId(task.id)}
                                    >
                                        <span className={styles.taskNum}>{i + 1}</span>
                                        <div className={styles.taskDefInfo}>
                                            <div className={styles.taskDefHeader}>
                                                <span className={styles.taskDefName}>{task.description}</span>
                                                <span className={styles.agentBadge}>{task.agent}</span>
                                            </div>
                                            {task.depends_on?.length > 0 ? (
                                                <div className={styles.taskDefMeta}>
                                                    <span className={styles.depArrow}>&larr;</span>
                                                    {task.depends_on.map((depId, j) => (
                                                        <span key={depId}>
                                                            {j > 0 && ', '}
                                                            <span className={styles.depName}>{taskMap[depId]?.description || depId}</span>
                                                        </span>
                                                    ))}
                                                </div>
                                            ) : (
                                                <div className={styles.taskDefMeta}>No dependencies</div>
                                            )}
                                        </div>
                                    </div>
                                ))}
                                {(!detail?.tasks || detail.tasks.length === 0) && (
                                    <div className={styles.emptyMsg}>No tasks defined</div>
                                )}
                            </>
                        )}
                    </div>
                </div>

                {/* Right pane: detail for selected item */}
                <div className={styles.detailPane}>
                    {tab === 'runs' && (
                        selectedRun
                            ? <RunDetail run={selectedRun} tasks={detail?.tasks} />
                            : <div className={styles.placeholder}>Select a run</div>
                    )}
                    {tab === 'tasks' && (
                        selectedTask
                            ? <TaskDetail task={selectedTask} taskMap={taskMap} />
                            : <div className={styles.placeholder}>Select a task</div>
                    )}
                </div>
            </div>
        </div>
    );
}
