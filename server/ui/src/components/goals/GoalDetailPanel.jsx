import { useState } from 'react';
import { StatusIcon, formatCron, formatTime, formatDuration } from './goalUtils.jsx';
import TaskOutputModal from './TaskOutputModal.jsx';
import styles from './GoalDetailPanel.module.css';

/**
 * Right panel showing goal detail with header, actions, and tabs.
 * Tabs: Runs | Task Definitions
 */
export default function GoalDetailPanel({
    goal,
    detail,
    isLoading,
    onBack,
    onDeleteGoal,
    onPauseGoal,
    onResumeGoal,
    onTriggerGoal,
}) {
    const [activeTab, setActiveTab] = useState('runs');
    const [selectedOutput, setSelectedOutput] = useState(null);

    if (!goal) {
        return (
            <div className={styles.empty}>
                <div className={styles.emptyText}>Select a goal to view details</div>
            </div>
        );
    }

    const isPaused = goal.status === 'paused';

    const handleRunNow = () => {
        onTriggerGoal(goal.id);
    };

    const handlePauseResume = () => {
        if (isPaused) {
            onResumeGoal(goal.id);
        } else {
            onPauseGoal(goal.id);
        }
    };

    const handleDelete = () => {
        if (window.confirm(`Delete goal "${goal.description}"?`)) {
            onDeleteGoal(goal.id);
        }
    };

    const runs = detail?.runs || [];
    const tasks = detail?.task_definitions || [];

    return (
        <div className={styles.container}>
            {/* Header */}
            <div className={styles.header}>
                <div className={styles.headerTop}>
                    <button className={styles.backBtn} onClick={onBack}>
                        ← Back
                    </button>
                </div>

                <div className={styles.headerMain}>
                    <div className={styles.titleRow}>
                        <div className={styles.statusIcon}>
                            <StatusIcon status={goal.status} size={18} />
                        </div>
                        <h2 className={styles.title}>{goal.description}</h2>
                    </div>

                    {goal.cron && (
                        <div className={styles.scheduleRow}>
                            <span className={styles.cronBadge}>
                                {formatCron(goal.cron)}
                            </span>
                            {goal.timezone && (
                                <span className={styles.timezone}>{goal.timezone}</span>
                            )}
                        </div>
                    )}
                </div>

                {/* Actions */}
                <div className={styles.actions}>
                    <button
                        className={styles.actionBtn}
                        onClick={handleRunNow}
                        disabled={isLoading}
                    >
                        ▶ Run Now
                    </button>
                    <button
                        className={styles.actionBtn}
                        onClick={handlePauseResume}
                        disabled={isLoading}
                    >
                        {isPaused ? '▶ Resume' : '⏸ Pause'}
                    </button>
                    <button
                        className={`${styles.actionBtn} ${styles.danger}`}
                        onClick={handleDelete}
                        disabled={isLoading}
                    >
                        🗑 Delete
                    </button>
                </div>
            </div>

            {/* Tabs */}
            <div className={styles.tabBar}>
                <button
                    className={`${styles.tab} ${activeTab === 'runs' ? styles.tabActive : ''}`}
                    onClick={() => setActiveTab('runs')}
                >
                    Runs ({runs.length})
                </button>
                <button
                    className={`${styles.tab} ${activeTab === 'tasks' ? styles.tabActive : ''}`}
                    onClick={() => setActiveTab('tasks')}
                >
                    Task Definitions ({tasks.length})
                </button>
            </div>

            {/* Tab Content */}
            <div className={styles.tabContent}>
                {activeTab === 'runs' && (
                    <RunsTab
                        runs={runs}
                        tasks={tasks}
                        onViewOutput={setSelectedOutput}
                    />
                )}
                {activeTab === 'tasks' && (
                    <TaskDefinitionsTab tasks={tasks} />
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

function RunsTab({ runs, tasks, onViewOutput }) {
    const [expandedRunId, setExpandedRunId] = useState(null);

    const taskMap = Object.fromEntries(tasks.map(t => [t.id, t]));

    if (runs.length === 0) {
        return <div className={styles.emptyTab}>No runs yet</div>;
    }

    return (
        <div className={styles.runsList}>
            {runs.map(run => (
                <RunItem
                    key={run.id}
                    run={run}
                    taskMap={taskMap}
                    isExpanded={run.id === expandedRunId}
                    onToggle={() => setExpandedRunId(
                        run.id === expandedRunId ? null : run.id
                    )}
                    onViewOutput={onViewOutput}
                />
            ))}
        </div>
    );
}

function RunItem({ run, taskMap, isExpanded, onToggle, onViewOutput }) {
    const completedCount = run.task_results?.filter(tr => tr.status === 'completed').length || 0;
    const totalCount = run.task_results?.length || 0;
    const duration = formatDuration(run.started_at, run.completed_at);

    return (
        <div className={styles.runItem}>
            <div className={styles.runHeader} onClick={onToggle}>
                <div className={styles.runToggle}>
                    {isExpanded ? '▼' : '▶'}
                </div>
                <div className={styles.runInfo}>
                    <div className={styles.runTitle}>
                        Run #{run.run_number}
                    </div>
                    <div className={styles.runMeta}>
                        {formatTime(run.created_at)}
                        {duration && ` · ${duration}`}
                        {' · '}
                        {completedCount}/{totalCount} tasks
                    </div>
                </div>
                <StatusIcon status={run.status} size={14} />
            </div>

            {isExpanded && run.task_results && (
                <div className={styles.taskResults}>
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
                                const taskDuration = formatDuration(
                                    taskResult.started_at,
                                    taskResult.completed_at
                                );
                                const hasOutput = taskResult.result || taskResult.error;

                                return (
                                    <tr key={taskResult.id}>
                                        <td>{task?.description || taskResult.task_id}</td>
                                        <td><span className={styles.agentBadge}>{task?.agent}</span></td>
                                        <td><StatusIcon status={taskResult.status} size={12} /></td>
                                        <td>{taskDuration || '-'}</td>
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
                                                    View Output
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

function TaskDefinitionsTab({ tasks }) {
    const [expandedTaskId, setExpandedTaskId] = useState(null);

    const taskMap = Object.fromEntries(tasks.map(t => [t.id, t]));

    if (tasks.length === 0) {
        return <div className={styles.emptyTab}>No task definitions</div>;
    }

    return (
        <div className={styles.tasksList}>
            {tasks.map((task, index) => (
                <div
                    key={task.id}
                    className={`${styles.taskDefItem} ${task.id === expandedTaskId ? styles.taskExpanded : ''}`}
                    onClick={() => setExpandedTaskId(
                        task.id === expandedTaskId ? null : task.id
                    )}
                >
                    <div className={styles.taskDefHeader}>
                        <div className={styles.taskNum}>{index + 1}</div>
                        <div className={styles.taskDefName}>{task.description}</div>
                        <span className={styles.agentBadge}>{task.agent}</span>
                        <div className={styles.taskToggle}>
                            {task.id === expandedTaskId ? '▼' : '▶'}
                        </div>
                    </div>

                    {task.id === expandedTaskId && (
                        <div className={styles.taskDefBody}>
                            <div className={styles.taskDefSection}>
                                <div className={styles.sectionLabel}>Instruction</div>
                                <div className={styles.sectionContent}>{task.instruction}</div>
                            </div>

                            {task.depends_on?.length > 0 && (
                                <div className={styles.taskDefSection}>
                                    <div className={styles.sectionLabel}>Dependencies</div>
                                    <div className={styles.sectionContent}>
                                        {task.depends_on.map(depId => (
                                            <div key={depId} className={styles.dependency}>
                                                → {taskMap[depId]?.description || depId}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            <div className={styles.taskMetaRow}>
                                <span>Max retries: {task.max_retries}</span>
                            </div>
                        </div>
                    )}
                </div>
            ))}
        </div>
    );
}
