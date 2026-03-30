import { useState, useEffect, useCallback, useRef } from 'react';

const POLL_INTERVAL = 5000;

export default function useGoals() {
    const [goals, setGoals] = useState([]);
    const [runnerStatus, setRunnerStatus] = useState(null);
    const [selectedGoalId, setSelectedGoalId] = useState(null);
    const [polling, setPolling] = useState(false);
    const _lastGoalsJson = useRef('');
    const _lastRunnerJson = useRef('');

    useEffect(() => {
        if (!polling) return;
        let active = true;
        const poll = async () => {
            const [goalsRes, runnerRes] = await Promise.all([
                fetch('/api/goals').then(r => r.json()).catch(() => null),
                fetch('/api/runner/status').then(r => r.json()).catch(() => null),
            ]);
            if (!active) return;
            if (goalsRes?.goals) {
                const json = JSON.stringify(goalsRes.goals);
                if (json !== _lastGoalsJson.current) {
                    _lastGoalsJson.current = json;
                    setGoals(goalsRes.goals);
                }
            }
            if (runnerRes) {
                const json = JSON.stringify(runnerRes);
                if (json !== _lastRunnerJson.current) {
                    _lastRunnerJson.current = json;
                    setRunnerStatus(runnerRes);
                }
            }
        };
        poll();
        const id = setInterval(poll, POLL_INTERVAL);
        return () => { active = false; clearInterval(id); };
    }, [polling]);

    const fetchGoalDetail = useCallback(async (goalId) => {
        const res = await fetch(`/api/goals/${goalId}`);
        return res.json();
    }, []);

    const deleteGoal = useCallback(async (goalId) => {
        await fetch(`/api/goals/${goalId}`, { method: 'DELETE' });
        setGoals(prev => prev.filter(g => g.id !== goalId));
        if (selectedGoalId === goalId) setSelectedGoalId(null);
    }, [selectedGoalId]);

    const deleteRun = useCallback(async (goalId, runId) => {
        await fetch(`/api/goals/${goalId}/runs/${runId}`, { method: 'DELETE' });
    }, []);

    const pauseGoal = useCallback(async (goalId) => {
        await fetch(`/api/goals/${goalId}/pause`, { method: 'POST' });
        setGoals(prev => prev.map(g => g.id === goalId ? { ...g, status: 'paused' } : g));
    }, []);

    const resumeGoal = useCallback(async (goalId) => {
        await fetch(`/api/goals/${goalId}/resume`, { method: 'POST' });
        setGoals(prev => prev.map(g => g.id === goalId ? { ...g, status: 'active' } : g));
    }, []);

    const triggerGoal = useCallback(async (goalId) => {
        const res = await fetch(`/api/goals/${goalId}/trigger`, { method: 'POST' });
        return res.json();
    }, []);

    const startPolling = useCallback(() => setPolling(true), []);
    const stopPolling = useCallback(() => setPolling(false), []);

    return {
        goals,
        runnerStatus,
        selectedGoalId,
        setSelectedGoalId,
        fetchGoalDetail,
        deleteGoal,
        deleteRun,
        pauseGoal,
        resumeGoal,
        triggerGoal,
        startPolling,
        stopPolling,
    };
}
