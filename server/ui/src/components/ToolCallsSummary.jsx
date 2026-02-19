import React, { useState, useRef } from 'react';
import styles from './ToolCallsSummary.module.css';
import WrenchIcon from './icons/WrenchIcon';

function formatName(name) {
    return name.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

export default function ToolCallsSummary({ toolCalls }) {
    const [toolsExpanded, setToolsExpanded] = useState(false);
    const [showLatestTool, setShowLatestTool] = useState(true);
    const latestToolRef = useRef(null);

    const toolSummary = toolCalls.reduce((acc, tool) => {
        acc[tool.name] = (acc[tool.name] || 0) + 1;
        return acc;
    }, {});

    const latestTool = toolCalls.length > 0 ? toolCalls[toolCalls.length - 1] : null;

    React.useEffect(() => {
        if (latestTool && latestTool !== latestToolRef.current) {
            latestToolRef.current = latestTool;
            setShowLatestTool(true);
            const timer = setTimeout(() => setShowLatestTool(false), 2000);
            return () => clearTimeout(timer);
        }
    }, [latestTool]);

    if (toolCalls.length === 0) return null;

    return (
        <>
            <span
                className={styles.toolSummaryText}
                onClick={() => setToolsExpanded(!toolsExpanded)}
            >
                <WrenchIcon size={12} />
                {' '}
                {showLatestTool && latestTool && (
                    <span className={styles.latestToolName}>
                        {formatName(latestTool.name)} •{' '}
                    </span>
                )}
                {toolCalls.length} tool{toolCalls.length !== 1 ? 's' : ''}
            </span>
            {toolsExpanded && (
                <div className={styles.toolList}>
                    {Object.entries(toolSummary).map(([name, count]) => (
                        <div key={name} className={styles.toolItem}>
                            {formatName(name)}{count > 1 && ` ×${count}`}
                        </div>
                    ))}
                </div>
            )}
        </>
    );
}
