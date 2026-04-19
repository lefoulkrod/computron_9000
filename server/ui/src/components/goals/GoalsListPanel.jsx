import { formatTime } from './goalUtils.jsx';
import Badge from '../Badge.jsx';
import ListItem from '../ListItem.jsx';
import styles from './GoalsListPanel.module.css';

/**
 * Left panel showing list of goals.
 * Uses shared Badge + ListItem primitives per the SIGNAL design language.
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
                <span className={styles.title}>Goals</span>
                <RunnerStatusBadge status={runnerStatus} />
            </div>

            <div className={styles.goalsList}>
                {sortedGoals.length === 0 ? (
                    <div className={styles.empty}>No goals yet</div>
                ) : (
                    sortedGoals.map(goal => {
                        const lastRunTime = goal.last_run_at ? formatTime(goal.last_run_at) : null;
                        const displayStatus = goal.is_running ? 'running' : goal.status;

                        return (
                            <ListItem
                                key={goal.id}
                                active={goal.id === selectedGoalId}
                                onClick={() => onSelectGoal(goal.id)}
                                name={goal.description}
                                description={lastRunTime ? `Last run ${lastRunTime}` : 'No runs yet'}
                                badges={
                                    <>
                                        <StatusBadge status={displayStatus} />
                                        {goal.cron && <Badge variant="neutral">{goal.cron}</Badge>}
                                    </>
                                }
                            />
                        );
                    })
                )}
            </div>
        </div>
    );
}

function StatusBadge({ status }) {
    const variants = {
        running: { variant: 'info', label: 'RUNNING' },
        active: { variant: 'success', label: 'ACTIVE' },
        completed: { variant: 'success', label: 'COMPLETE' },
        failed: { variant: 'danger', label: 'ERROR' },
        paused: { variant: 'neutral', label: 'PAUSED' },
        pending: { variant: 'neutral', label: 'PENDING' },
    };
    const v = variants[status] || { variant: 'neutral', label: String(status || '').toUpperCase() };
    return <Badge variant={v.variant}>{v.label}</Badge>;
}

function RunnerStatusBadge({ status }) {
    if (status === 'running') {
        return <span className={`${styles.runnerStatus} ${styles.runnerActive}`}><i className="bi bi-lightning-charge-fill" /> ACTIVE</span>;
    }
    if (status === 'error') {
        return <span className={`${styles.runnerStatus} ${styles.runnerError}`}><i className="bi bi-exclamation-triangle" /> ERROR</span>;
    }
    return <span className={`${styles.runnerStatus} ${styles.runnerIdle}`}><i className="bi bi-circle" /> IDLE</span>;
}
