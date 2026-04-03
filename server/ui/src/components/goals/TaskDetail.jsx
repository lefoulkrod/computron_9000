import styles from './TaskDetail.module.css';

export default function TaskDetail({ task, taskMap }) {
    if (!task) return null;

    const deps = (task.depends_on || []).map(id => taskMap[id]?.description || id);

    return (
        <div className={styles.container}>
            <div className={styles.title}>
                {task.description}
                <span className={styles.agentBadge}>{task.agent}</span>
            </div>

            <div className={styles.kvRow}>
                <div className={styles.kvItem}>
                    <div className={styles.label}>Agent</div>
                    <div className={styles.value}>{task.agent}</div>
                </div>
                <div className={styles.kvItem}>
                    <div className={styles.label}>Max Retries</div>
                    <div className={styles.value}>{task.max_retries}</div>
                </div>
                <div className={styles.kvItem}>
                    <div className={styles.label}>Dependencies</div>
                    <div className={`${styles.value} ${deps.length === 0 ? styles.muted : ''}`}>
                        {deps.length > 0 ? deps.join(', ') : 'None'}
                    </div>
                </div>
            </div>

            <div className={styles.section}>
                <div className={styles.label}>Instruction</div>
                <div className={styles.instruction}>{task.instruction}</div>
            </div>
        </div>
    );
}
