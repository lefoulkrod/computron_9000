import { useState, useEffect, useCallback, useRef } from 'react';

const POLL_INTERVAL = 5000;

/**
 * Goals state hook. Polls automatically whenever the goals panel is open
 * (panelOpen=true) or a goal is selected for detail view.
 */
export default function useGoals(panelOpen) {
    const [goals, setGoals] = useState([]);
    const [runnerStatus, setRunnerStatus] = useState(null);
    const [selectedGoalId, setSelectedGoalId] = useState(null);
    const _lastGoalsJson = useRef('');
    const _lastRunnerJson = useRef('');

    // Reset selection each time the panel opens fresh.
    const prevOpen = useRef(false);
    useEffect(() => {
        if (panelOpen && !prevOpen.current) {
            setSelectedGoalId(null);
        }
        prevOpen.current = panelOpen;
    }, [panelOpen]);

    // Poll while panel is open or a goal detail is showing.
    const shouldPoll = panelOpen || !!selectedGoalId;
    useEffect(() => {
        if (!shouldPoll) return;
        let active = true;
        const poll = async () => {
            const [goalsRes, runnerRes] = await Promise.all([
                fetch('/api/goals').then(r => r.json()).catch(() => null),
                fetch('/api/runner/status').then(r => r.json()).catch(() => null),
            ]);
            if (!active) return;
            const runningIds = new Set(runnerRes?.running_goal_ids || []);
            if (goalsRes?.goals) {
                const enriched = goalsRes.goals.map(g => ({
                    ...g,
                    is_running: runningIds.has(g.id),
                }));
                const json = JSON.stringify(enriched);
                if (json !== _lastGoalsJson.current) {
                    _lastGoalsJson.current = json;
                    setGoals(enriched);
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
    }, [shouldPoll]);

    const fetchGoalDetail = useCallback(async (goalId) => {
        const res = await fetch(`/api/goals/${goalId}`);
        return res.json();
    }, []);

    const deleteGoal = useCallback(async (goalId) => {
        await fetch(`/api/goals/${goalId}`, { method: 'DELETE', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
        setGoals(prev => prev.filter(g => g.id !== goalId));
        if (selectedGoalId === goalId) setSelectedGoalId(null);
    }, [selectedGoalId]);

    const deleteRun = useCallback(async (goalId, runId) => {
        await fetch(`/api/goals/${goalId}/runs/${runId}`, { method: 'DELETE', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
    }, []);

    const pauseGoal = useCallback(async (goalId) => {
        await fetch(`/api/goals/${goalId}/pause`, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
        setGoals(prev => prev.map(g => g.id === goalId ? { ...g, status: 'paused' } : g));
    }, []);

    const resumeGoal = useCallback(async (goalId) => {
        await fetch(`/api/goals/${goalId}/resume`, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
        setGoals(prev => prev.map(g => g.id === goalId ? { ...g, status: 'active' } : g));
    }, []);

    const triggerGoal = useCallback(async (goalId) => {
        const res = await fetch(`/api/goals/${goalId}/trigger`, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
        return res.json();
    }, []);

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
    };
}
