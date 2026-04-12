import { useMemo } from 'react';
import { StatusIcon, formatTime, formatDuration } from './goalUtils.jsx';
import styles from './RunDetail.module.css';

export default function RunDetail({ run, tasks }) {
    const taskMap = useMemo(
        () => Object.fromEntries((tasks || []).map(t => [t.id, t])),
        [tasks],
    );

    if (!run) return null;

    const completedCount = run.task_results?.filter(tr => tr.status === 'completed').length || 0;
    const totalCount = run.task_results?.length || 0;

    return (
        <div className={styles.container}>
            <div className={styles.runHeader}>
                <span className={styles.runTitle}>Run #{run.run_number}</span>
                <span className={styles.runMeta}>
                    {formatTime(run.created_at)}
                    {run.completed_at && ` \u00B7 ${formatDuration(run.started_at, run.completed_at)}`}
                    {` \u00B7 ${completedCount}/${totalCount} tasks`}
                </span>
            </div>
            {run.task_results?.map(tr => {
                const task = taskMap[tr.task_id];
                return (
                    <div key={tr.id} className={styles.taskResult}>
                        <div className={styles.taskHeader}>
                            <StatusIcon status={tr.status} />
                            <span className={styles.taskName}>{task?.description || tr.task_id}</span>
                            <span className={styles.agentBadge}>{task?.agent_profile_name || task?.agent_profile || '—'}</span>
                            {tr.completed_at && (
                                <span className={styles.duration}>
                                    {formatDuration(tr.started_at, tr.completed_at)}
                                </span>
                            )}
                        </div>
                        {tr.result && (
                            <div className={styles.taskBody}>
                                <div className={styles.resultText}>{tr.result}</div>
                            </div>
                        )}
                        {tr.error && (
                            <div className={styles.taskBody}>
                                <div className={`${styles.resultText} ${styles.errorText}`}>{tr.error}</div>
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
}
