import { useState, useEffect, useCallback, useRef } from 'react';
import shared from './CustomToolsPanel.module.css';
import styles from './SkillsPanel.module.css';
import TrashIcon from './icons/TrashIcon.jsx';

export default function SkillsPanel({ refreshSignal }) {
    const [skills, setSkills] = useState([]);
    const [loading, setLoading] = useState(true);
    const [deleting, setDeleting] = useState(null);
    const [collapsed, setCollapsed] = useState(false);
    const [newSkillIds, setNewSkillIds] = useState(new Set());
    const [hoveredSkill, setHoveredSkill] = useState(null);
    const [tooltipPos, setTooltipPos] = useState(null);
    const prevIdsRef = useRef(new Set());

    const fetchSkills = useCallback(async () => {
        try {
            const resp = await fetch('/api/skills');
            if (resp.ok) {
                const fresh = await resp.json();
                const freshIds = new Set(fresh.map(s => s.name));
                const added = fresh.filter(s => !prevIdsRef.current.has(s.name)).map(s => s.name);
                prevIdsRef.current = freshIds;
                if (added.length > 0) {
                    setNewSkillIds(new Set(added));
                    setTimeout(() => setNewSkillIds(new Set()), 700);
                }
                setSkills(fresh);
            }
        } catch (_) {
            // ignore
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchSkills();
    }, [fetchSkills]);

    useEffect(() => {
        if (refreshSignal > 0) fetchSkills();
    }, [refreshSignal, fetchSkills]);

    const handleDelete = async (name) => {
        setDeleting(name);
        try {
            const resp = await fetch(`/api/skills/${encodeURIComponent(name)}`, { method: 'DELETE' });
            if (resp.ok || resp.status === 404) {
                setSkills(prev => prev.filter(s => s.name !== name));
            }
        } catch (_) {
            // ignore
        } finally {
            setDeleting(null);
        }
    };

    const handleMouseEnter = (e, skill) => {
        if (!Array.isArray(skill.steps) || skill.steps.length === 0) return;
        const rect = e.currentTarget.getBoundingClientRect();
        setTooltipPos({ top: rect.top, left: rect.right + 8 });
        setHoveredSkill(skill);
    };

    const handleMouseLeave = () => {
        setHoveredSkill(null);
        setTooltipPos(null);
    };

    if (loading) return null;
    if (skills.length === 0) return null;

    return (
        <div className={shared.panel}>
            <div className={shared.header} onClick={() => setCollapsed(c => !c)}>
                <span className={shared.title}>Skills <span className={shared.count}>{skills.length}</span></span>
                <span className={shared.chevron}>{collapsed ? '▶' : '▼'}</span>
            </div>
            {!collapsed && (
                <ul className={shared.list}>
                    {skills.map(skill => (
                        <li
                            key={skill.name}
                            className={`${shared.item} ${newSkillIds.has(skill.name) ? shared.itemNew : ''}`}
                            onMouseEnter={(e) => handleMouseEnter(e, skill)}
                            onMouseLeave={handleMouseLeave}
                        >
                            <div className={shared.itemMain}>
                                <span className={shared.name}>{skill.name}</span>
                            </div>
                            <p className={shared.desc}>{skill.description}</p>
                            {(skill.usage_count ?? 0) > 0 && (
                                <span className={styles.stats}>
                                    used {skill.usage_count}×
                                </span>
                            )}
                            <button
                                className={shared.deleteBtn}
                                onClick={() => handleDelete(skill.name)}
                                disabled={deleting === skill.name}
                                title="Delete skill"
                            >
                                {deleting === skill.name ? '…' : <TrashIcon size={13} />}
                            </button>
                        </li>
                    ))}
                </ul>
            )}
            {hoveredSkill && tooltipPos && (
                <div
                    className={styles.tooltip}
                    style={{ top: tooltipPos.top, left: tooltipPos.left }}
                >
                    <div className={styles.tooltipTitle}>Steps</div>
                    <ol className={styles.tooltipSteps}>
                        {hoveredSkill.steps.map((step, i) => (
                            <li key={i}>
                                <span className={styles.tooltipTool}>{step.tool}</span>
                                <span className={styles.tooltipDesc}>{step.description}</span>
                            </li>
                        ))}
                    </ol>
                </div>
            )}
        </div>
    );
}
