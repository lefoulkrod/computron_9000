import { useState } from 'react';
import { formatCron, formatTime, formatTimeUntil, formatDuration } from './goalUtils.jsx';
import TaskOutputModal from './TaskOutputModal.jsx';
import styles from './GoalDetailPanel.module.css';

/**
 * Helper function to calculate next run from cron expression.
 * Supports basic cron patterns (minute hour * * *)
 */
function getNextRun(cron) {
    if (!cron) return null;

    const now = new Date();
    const next = new Date(now);

    const parts = cron.split(' ');
    if (parts.length >= 5) {
        const minute = parts[0];
        const hour = parts[1];

        if (minute !== '*' && hour !== '*') {
            next.setHours(parseInt(hour), parseInt(minute), 0, 0);
            if (next <= now) {
                next.setDate(next.getDate() + 1);
            }
            return next;
        }
    }
    return null;
}

function statusDotClass(status, isRunning) {
    if (isRunning || status === 'running') return styles.statusDotRunning;
    if (status === 'completed' || status === 'active') return styles.statusDotComplete;
    if (status === 'failed') return styles.statusDotError;
    return '';
}

function statusLabel(status, isRunning) {
    if (isRunning) return 'RUNNING';
    if (status === 'paused') return 'PAUSED';
    if (status === 'failed') return 'ERROR';
    if (status === 'completed') return 'COMPLETE';
    if (status === 'active') return 'ACTIVE GOAL';
    return String(status || '').toUpperCase();
}

/**
 * Right panel showing goal detail.
 * Layout: actions bar + sticky heading (title + schedule) + tabs (RECENT RUNS / TASKS) + tab content.
 */
export default function GoalDetailPanel({
    goal,
    detail,
    isLoading,
    onDeleteGoal,
    onDeleteRun,
    onPauseGoal,
    onResumeGoal,
    onTriggerGoal,
}) {
    const [activeTab, setActiveTab] = useState('runs');
    const [selectedOutput, setSelectedOutput] = useState(null);
    const [confirmDelete, setConfirmDelete] = useState(false);

    if (!goal) {
        return (
            <div className={styles.empty}>
                <div className={styles.emptyText}>Select a goal to view details</div>
            </div>
        );
    }

    const isPaused = goal.status === 'paused';
    const nextRun = getNextRun(goal.cron);

    const handleRunNow = () => onTriggerGoal(goal.id);

    const handlePauseResume = () => {
        if (isPaused) onResumeGoal(goal.id);
        else onPauseGoal(goal.id);
    };

    const handleDelete = () => {
        if (!confirmDelete) {
            setConfirmDelete(true);
            setTimeout(() => setConfirmDelete(false), 3000);
            return;
        }
        onDeleteGoal(goal.id);
    };

    const runs = detail?.runs || [];
    const tasks = detail?.tasks || [];

    return (
        <div className={styles.container}>
            {/* Actions bar */}
            <div className={styles.actionsBar}>
                <span className={styles.activeLabel}>
                    <span className={`${styles.statusDot} ${statusDotClass(goal.status, goal.is_running)}`} />
                    {statusLabel(goal.status, goal.is_running)}
                </span>
                <div className={styles.actionsRight}>
                    <button
                        className={styles.actionBtn}
                        onClick={handlePauseResume}
                        disabled={isLoading}
                    >
                        {isPaused
                            ? <><i className="bi bi-play-fill" /> RESUME</>
                            : <><i className="bi bi-pause-fill" /> PAUSE</>
                        }
                    </button>
                    <button
                        className={`${styles.actionBtn} ${styles.success}`}
                        onClick={handleRunNow}
                        disabled={isLoading}
                    >
                        <i className="bi bi-play-fill" /> RUN NOW
                    </button>
                    <button
                        className={`${styles.actionBtn} ${styles.danger}`}
                        onClick={handleDelete}
                        disabled={isLoading}
                    >
                        <i className="bi bi-trash3" /> {confirmDelete ? 'CONFIRM?' : 'DELETE'}
                    </button>
                </div>
            </div>

            {/* Heading block */}
            <div className={styles.headingBlock}>
                <h2 className={styles.title}>{goal.description}</h2>
                {goal.cron && (
                    <div className={styles.schedule}>
                        <span className={styles.cronChip}>{formatCron(goal.cron)}</span>
                        {goal.timezone && <span className={styles.timezone}>{goal.timezone}</span>}
                        {nextRun && <span className={styles.nextRun}>Next: {formatTimeUntil(nextRun)}</span>}
                    </div>
                )}
            </div>

            {/* Tabs */}
            <div className={styles.tabs}>
                <button
                    className={`${styles.tab} ${activeTab === 'runs' ? styles.tabActive : ''}`}
                    onClick={() => setActiveTab('runs')}
                >
                    Recent Runs
                    <span className={styles.tabCount}>{runs.length}</span>
                </button>
                <button
                    className={`${styles.tab} ${activeTab === 'tasks' ? styles.tabActive : ''}`}
                    onClick={() => setActiveTab('tasks')}
                >
                    Tasks
                    <span className={styles.tabCount}>{tasks.length}</span>
                </button>
            </div>

            {/* Tab content */}
            <div className={styles.tabContent}>
                {activeTab === 'runs' && (
                    <RunsTab
                        runs={runs}
                        tasks={tasks}
                        goalId={goal.id}
                        onViewOutput={setSelectedOutput}
                        onDeleteRun={onDeleteRun}
                    />
                )}
                {activeTab === 'tasks' && (
                    <TasksTab tasks={tasks} />
                )}
            </div>

            {/* Output Modal */}
            {selectedOutput && (
                <TaskOutputModal
                    output={selectedOutput.output}
                    taskName={selectedOutput.taskName}
                    runNumber={selectedOutput.runNumber}
                    onClose={() => setSelectedOutput(null)}
                />
            )}
        </div>
    );
}

function RunsTab({ runs, tasks, goalId, onViewOutput, onDeleteRun }) {
    const [expandedRunId, setExpandedRunId] = useState(null);
    const taskMap = Object.fromEntries(tasks.map(t => [t.id, t]));

    if (runs.length === 0) {
        return <div className={styles.emptyTab}>No runs yet</div>;
    }

    return (
        <div className={styles.rowList}>
            {runs.map(run => (
                <RunRow
                    key={run.id}
                    run={run}
                    taskMap={taskMap}
                    isExpanded={run.id === expandedRunId}
                    onToggle={() => setExpandedRunId(run.id === expandedRunId ? null : run.id)}
                    onViewOutput={onViewOutput}
                    onDelete={() => onDeleteRun(goalId, run.id)}
                />
            ))}
        </div>
    );
}

function RunRow({ run, taskMap, isExpanded, onToggle, onViewOutput, onDelete }) {
    const completedCount = run.task_results?.filter(tr => tr.status === 'completed').length || 0;
    const totalCount = run.task_results?.length || 0;
    const duration = formatDuration(run.started_at, run.completed_at);

    const badgeClass =
        run.status === 'completed' ? styles.rowBadgeComplete
        : run.status === 'failed' ? styles.rowBadgeError
        : styles.rowBadgeReady;
    const badgeLabel =
        run.status === 'completed' ? 'COMPLETE'
        : run.status === 'failed' ? 'FAILED'
        : String(run.status || '').toUpperCase();
    const dotClass =
        run.status === 'completed' ? styles.statusDotComplete
        : run.status === 'failed' ? styles.statusDotError
        : run.status === 'running' ? styles.statusDotRunning
        : '';

    return (
        <div className={styles.row}>
            <div className={styles.rowHead} onClick={onToggle}>
                <span className={styles.chevron}>
                    <i className={`bi bi-chevron-${isExpanded ? 'down' : 'right'}`} />
                </span>
                <span className={`${styles.statusDot} ${dotClass}`} />
                <div className={styles.rowMain}>
                    <span className={styles.rowTitle}>Run #{run.run_number}</span>
                    <span className={styles.rowMeta}>
                        {formatTime(run.created_at)}
                        {duration && ` · ${duration}`}
                        {' · '}
                        {completedCount}/{totalCount} tasks
                    </span>
                </div>
                <span className={`${styles.rowBadge} ${badgeClass}`}>{badgeLabel}</span>
                <button
                    className={styles.rowDeleteBtn}
                    onClick={(e) => { e.stopPropagation(); onDelete(); }}
                    title="Delete run"
                >
                    <i className="bi bi-trash3" />
                </button>
            </div>

            {isExpanded && run.task_results && (
                <div className={styles.rowBody}>
                    <table className={styles.resultsTable}>
                        <thead>
                            <tr>
                                <th>Task</th>
                                <th>Agent</th>
                                <th>Status</th>
                                <th>Duration</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {run.task_results.map(taskResult => {
                                const task = taskMap[taskResult.task_id];
                                const taskDuration = formatDuration(taskResult.started_at, taskResult.completed_at);
                                const hasOutput = taskResult.result || taskResult.error;
                                const trDotClass =
                                    taskResult.status === 'completed' ? styles.statusDotComplete
                                    : taskResult.status === 'failed' ? styles.statusDotError
                                    : taskResult.status === 'running' ? styles.statusDotRunning
                                    : '';

                                return (
                                    <tr key={taskResult.id}>
                                        <td>{task?.description || taskResult.task_id}</td>
                                        <td>
                                            <span className={`${styles.rowBadge} ${styles.rowBadgeAgent}`}>
                                                {task?.agent_profile_name || '—'}
                                            </span>
                                        </td>
                                        <td><span className={`${styles.statusDot} ${trDotClass}`} /></td>
                                        <td>{taskDuration || <span className={styles.skipped}>—</span>}</td>
                                        <td>
                                            {hasOutput && (
                                                <button
                                                    className={styles.viewOutputBtn}
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        onViewOutput({
                                                            output: taskResult.result || taskResult.error,
                                                            taskName: task?.description || taskResult.task_id,
                                                            runNumber: run.run_number,
                                                        });
                                                    }}
                                                >
                                                    View output
                                                </button>
                                            )}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}

function TasksTab({ tasks }) {
    const [expandedTaskId, setExpandedTaskId] = useState(null);
    const taskMap = Object.fromEntries(tasks.map(t => [t.id, t]));

    if (tasks.length === 0) {
        return <div className={styles.emptyTab}>No task definitions</div>;
    }

    return (
        <div className={styles.rowList}>
            {tasks.map((task, index) => (
                <TaskRow
                    key={task.id}
                    task={task}
                    index={index}
                    taskMap={taskMap}
                    isExpanded={task.id === expandedTaskId}
                    onToggle={() => setExpandedTaskId(task.id === expandedTaskId ? null : task.id)}
                />
            ))}
        </div>
    );
}

function TaskRow({ task, index, taskMap, isExpanded, onToggle }) {
    return (
        <div className={styles.row}>
            <div className={styles.rowHead} onClick={onToggle}>
                <span className={styles.chevron}>
                    <i className={`bi bi-chevron-${isExpanded ? 'down' : 'right'}`} />
                </span>
                <span className={styles.num}>{String(index + 1).padStart(2, '0')}</span>
                <div className={styles.rowMain}>
                    <span className={styles.rowTitle}>{task.description}</span>
                    <span className={styles.rowMeta}>
                        agent: {task.agent_profile_name || task.agent_profile || '—'}
                        {task.depends_on?.length > 0 && ` · depends on ${task.depends_on.length}`}
                    </span>
                </div>
                <span className={`${styles.rowBadge} ${styles.rowBadgeReady}`}>READY</span>
            </div>

            {isExpanded && (
                <div className={styles.rowBody}>
                    <div className={styles.detailSection}>
                        <div className={styles.detailLabel}>Instruction</div>
                        <div className={styles.detailContent}>{task.instruction}</div>
                    </div>

                    {task.depends_on?.length > 0 && (
                        <div className={styles.detailSection}>
                            <div className={styles.detailLabel}>Depends on</div>
                            <div className={styles.detailContent}>
                                {task.depends_on.map(depId => (
                                    <div key={depId} className={styles.dependency}>
                                        → {taskMap[depId]?.description || depId}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    <div className={styles.detailMeta}>
                        <span><strong>Max retries:</strong> {task.max_retries}</span>
                    </div>
                </div>
            )}
        </div>
    );
}
