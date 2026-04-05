import { formatTime } from './goalUtils.jsx';
import shared from '../CustomToolsPanel.module.css';
import styles from './GoalsListPanel.module.css';

/**
 * Left panel showing list of goals.
 * Uses the same shared list styles as ConversationsPanel / CustomToolsPanel.
 */
export default function GoalsListPanel({ goals, runnerStatus, selectedGoalId, onSelectGoal }) {
    const sortedGoals = [...goals].sort((a, b) => {
        const statusOrder = { running: 0, active: 1, pending: 2, paused: 3, completed: 4, failed: 5 };
        const aStatus = a.is_running ? 'running' : a.status;
        const bStatus = b.is_running ? 'running' : b.status;
        const aOrder = statusOrder[aStatus] ?? 5;
        const bOrder = statusOrder[bStatus] ?? 5;
        if (aOrder !== bOrder) return aOrder - bOrder;

        const aTime = a.last_run_at ? new Date(a.last_run_at) : 0;
        const bTime = b.last_run_at ? new Date(b.last_run_at) : 0;
        return bTime - aTime;
    });

    return (
        <div className={styles.container}>
            <div className={styles.header}>
                <div className={styles.title}>Goals</div>
                <div className={styles.runnerStatus}>
                    <RunnerStatusBadge status={runnerStatus} />
                </div>
            </div>

            <div className={styles.goalsList}>
                {sortedGoals.length === 0 ? (
                    <div className={shared.empty}>No goals yet</div>
                ) : (
                    sortedGoals.map(goal => {
                        const lastRunTime = goal.last_run_at ? formatTime(goal.last_run_at) : null;
                        const isSelected = goal.id === selectedGoalId;
                        const displayStatus = goal.is_running ? 'running' : goal.status;

                        return (
                            <div
                                key={goal.id}
                                className={`${shared.item} ${isSelected ? styles.itemSelected : ''}`}
                                onClick={() => onSelectGoal(goal.id)}
                                style={{ cursor: 'pointer' }}
                            >
                                <div className={shared.itemMain}>
                                    <span className={`${shared.name} ${styles.goalName}`}>{goal.description}</span>
                                </div>
                                <p className={shared.desc}>
                                    {lastRunTime ? `Last run ${lastRunTime}` : 'No runs yet'}
                                </p>
                                <div className={styles.statusBadge} style={{ color: getStatusColor(displayStatus), borderColor: getStatusColor(displayStatus) }}>
                                    {displayStatus}
                                </div>
                            </div>
                        );
                    })
                )}
            </div>
        </div>
    );
}

function RunnerStatusBadge({ status }) {
    if (status === 'running') {
        return <span className={styles.runnerActive}>⚡ Runner Active</span>;
    }
    if (status === 'error') {
        return <span className={styles.runnerError}>⚠ Runner Error</span>;
    }
    return <span className={styles.runnerIdle}>○ Runner Idle</span>;
}

function getStatusColor(status) {
    const colors = {
        active: 'var(--text)',
        completed: '#4ade80',
        running: '#22d3ee',
        failed: '#f87171',
        pending: 'var(--muted)',
        paused: '#fbbf24',
    };
    return colors[status] || 'var(--muted)';
}
