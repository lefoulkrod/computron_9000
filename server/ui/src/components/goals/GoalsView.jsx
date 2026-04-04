import { useState, useEffect } from 'react';
import GoalsListPanel from './GoalsListPanel.jsx';
import GoalDetailPanel from './GoalDetailPanel.jsx';
import styles from './GoalsView.module.css';

/**
 * Split-screen Goals view (35% left list, 65% right detail).
 * Main container for the new Goals UI.
 */
export default function GoalsView({
    goals,
    runnerStatus,
    selectedGoalId,
    setSelectedGoalId,
    deleteGoal,
    deleteRun,
    pauseGoal,
    resumeGoal,
    triggerGoal,
    fetchDetail,  // Passed from useGoals hook
}) {
    const [detail, setDetail] = useState(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);

    // Fetch detail when selected goal changes
    useEffect(() => {
        if (!selectedGoalId) {
            setDetail(null);
            setError(null);
            return;
        }

        setIsLoading(true);
        setError(null);

        fetchDetail(selectedGoalId)
            .then(data => {
                setDetail(data);
            })
            .catch(err => {
                setError(err.message);
                setDetail(null);
            })
            .finally(() => {
                setIsLoading(false);
            });
    }, [selectedGoalId, fetchDetail]);

    // Refresh detail periodically if goal is running
    useEffect(() => {
        if (!selectedGoalId || !detail) return;

        const goal = goals.find(g => g.id === selectedGoalId);
        const shouldPoll = goal?.status === 'running' || goal?.current_run_id;

        if (!shouldPoll) return;

        const interval = setInterval(() => {
            fetchDetail(selectedGoalId)
                .then(data => setDetail(data))
                .catch(err => console.error('Poll error:', err));
        }, 5000);

        return () => clearInterval(interval);
    }, [selectedGoalId, detail, goals, fetchDetail]);

    // Clear selection on unmount
    useEffect(() => {
        return () => {
            setSelectedGoalId(null);
        };
    }, [setSelectedGoalId]);

    const handleBack = () => {
        setSelectedGoalId(null);
    };

    const selectedGoal = goals.find(g => g.id === selectedGoalId) || null;

    return (
        <div className={styles.container}>
            <div className={styles.leftPanel}>
                <GoalsListPanel
                    goals={goals}
                    runnerStatus={runnerStatus}
                    selectedGoalId={selectedGoalId}
                    onSelectGoal={setSelectedGoalId}
                />
            </div>
            <div className={styles.rightPanel}>
                {error && (
                    <div className={styles.errorBanner}>
                        Error loading goal: {error}
                    </div>
                )}
                <GoalDetailPanel
                    goal={selectedGoal}
                    detail={detail}
                    isLoading={isLoading}
                    onBack={handleBack}
                    onDeleteGoal={deleteGoal}
                    onPauseGoal={pauseGoal}
                    onResumeGoal={resumeGoal}
                    onTriggerGoal={triggerGoal}
                />
            </div>
        </div>
    );
}
