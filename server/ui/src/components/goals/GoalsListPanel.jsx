import { StatusIcon, formatTime, formatDuration } from './goalUtils.jsx';
import styles from './GoalsListPanel.module.css';

/**
 * Left panel showing list of goal cards.
 * Clicking a card selects it.
 */
export default function GoalsListPanel({ goals, runnerStatus, selectedGoalId, onSelectGoal }) {
    // Sort: active/running first, then by last run time
    const sortedGoals = [...goals].sort((a, b) => {
        const statusOrder = { running: 0, pending: 1, completed: 2, failed: 3, paused: 4 };
        const aOrder = statusOrder[a.status] ?? 5;
        const bOrder = statusOrder[b.status] ?? 5;
        if (aOrder !== bOrder) return aOrder - bOrder;
        
        const aTime = a.last_run_at || 0;
        const bTime = b.last_run_at || 0;
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
                    <div className={styles.empty}>No goals yet</div>
                ) : (
                    sortedGoals.map(goal => (
                        <GoalCard
                            key={goal.id}
                            goal={goal}
                            isSelected={goal.id === selectedGoalId}
                            onClick={() => onSelectGoal(goal.id)}
                        />
                    ))
                )}
            </div>
        </div>
    );
}

function GoalCard({ goal, isSelected, onClick }) {
    const statusColor = getStatusColor(goal.status);
    const runCount = goal.run_count || 0;
    const lastRunTime = goal.last_run_at ? formatTime(goal.last_run_at) : 'Never';

    return (
        <button
            className={`${styles.card} ${isSelected ? styles.cardSelected : ''}`}
            onClick={onClick}
        >
            <div className={styles.cardHeader}>
                <div className={styles.name}>{goal.description}</div>
                <div className={styles.statusBadge} style={{ borderColor: statusColor, color: statusColor }}>
                    {goal.status}
                </div>
            </div>

            <div className={styles.cardMeta}>
                <span className={styles.metaItem}>
                    Runs: {runCount}
                </span>
                <span className={styles.metaItem}>
                    {lastRunTime}
                </span>
            </div>

            {goal.current_run_id && (
                <div className={styles.currentRun}>
                    <StatusIcon status="running" size={10} />
                    <span>Running now...</span>
                </div>
            )}
        </button>
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
        completed: '#4ade80',
        running: '#fbbf24',
        failed: '#f87171',
        pending: 'var(--muted)',
        paused: '#a78bfa',
    };
    return colors[status] || 'var(--muted)';
}
