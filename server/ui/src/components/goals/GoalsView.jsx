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
    const [refreshCounter, setRefreshCounter] = useState(0);

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
    }, [selectedGoalId, fetchDetail, refreshCounter]);

    // Refresh detail periodically while a goal is selected
    useEffect(() => {
        if (!selectedGoalId) return;

        const interval = setInterval(() => {
            fetchDetail(selectedGoalId)
                .then(data => setDetail(data))
                .catch(() => {});
        }, 5000);

        return () => clearInterval(interval);
    }, [selectedGoalId, fetchDetail]);

    // Clear selection on unmount
    useEffect(() => {
        return () => {
            setSelectedGoalId(null);
        };
    }, [setSelectedGoalId]);

    const refresh = () => setRefreshCounter(c => c + 1);

    const handleTrigger = async (goalId) => {
        await triggerGoal(goalId);
        refresh();
    };

    const handlePause = async (goalId) => {
        await pauseGoal(goalId);
        refresh();
    };

    const handleResume = async (goalId) => {
        await resumeGoal(goalId);
        refresh();
    };

    const handleDelete = async (goalId) => {
        await deleteGoal(goalId);
    };

    const handleDeleteRun = async (goalId, runId) => {
        await deleteRun(goalId, runId);
        refresh();
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
                    onDeleteGoal={handleDelete}
                    onDeleteRun={handleDeleteRun}
                    onPauseGoal={handlePause}
                    onResumeGoal={handleResume}
                    onTriggerGoal={handleTrigger}
                />
            </div>
        </div>
    );
}
