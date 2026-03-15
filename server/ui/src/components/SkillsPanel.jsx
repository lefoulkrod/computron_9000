import { useState } from 'react';
import shared from './CustomToolsPanel.module.css';
import styles from './SkillsPanel.module.css';
import TrashIcon from './icons/TrashIcon.jsx';
import useListPanel from '../hooks/useListPanel.js';

export default function SkillsPanel({ refreshSignal }) {
    const {
        items: skills, loading, collapsed, setCollapsed,
        deleting, handleDelete, newItemIds,
    } = useListPanel('/api/skills', {
        refreshSignal,
        getId: (s) => s.name,
    });

    const [hoveredSkill, setHoveredSkill] = useState(null);
    const [tooltipPos, setTooltipPos] = useState(null);

    const onDelete = (name) => {
        handleDelete(name, `/api/skills/${encodeURIComponent(name)}`, (s) => s.name !== name);
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

    if (loading || skills.length === 0) return null;

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
                            className={`${shared.item} ${newItemIds.has(skill.name) ? shared.itemNew : ''}`}
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
                                onClick={() => onDelete(skill.name)}
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
