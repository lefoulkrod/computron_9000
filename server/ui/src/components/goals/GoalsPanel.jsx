import { StatusIcon } from './goalUtils.jsx';
import styles from './GoalsPanel.module.css';

export default function GoalsPanel({ goals, runnerStatus, onSelectGoal }) {
    return (
        <div className={styles.container}>
            {runnerStatus && (
                <div className={styles.runnerBar}>
                    <span className={styles.runnerLabel}>
                        Runner: {runnerStatus.paused ? 'paused' : runnerStatus.running ? 'active' : 'stopped'}
                    </span>
                    <span className={styles.runnerMeta}>
                        {runnerStatus.active_tasks}/{runnerStatus.max_concurrent} slots
                    </span>
                </div>
            )}
            {goals.length === 0 && (
                <div className={styles.empty}>
                    No goals yet. Ask the agent to create one.
                </div>
            )}
            <ul className={styles.list}>
                {goals.map(goal => (
                    <li
                        key={goal.id}
                        className={styles.item}
                        onClick={() => onSelectGoal(goal.id)}
                    >
                        <div className={styles.itemHeader}>
                            <StatusIcon status={goal.status} size={12} />
                            <span className={styles.itemTitle}>{goal.description}</span>
                        </div>
                        <div className={styles.itemMeta}>
                            {goal.cron && <span className={styles.cron}>{goal.cron}</span>}
                            <span className={styles.status}>{goal.status}</span>
                        </div>
                    </li>
                ))}
            </ul>
        </div>
    );
}
