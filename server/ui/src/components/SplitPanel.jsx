import styles from './SplitPanel.module.css';

/**
 * Master-detail layout shell per the SIGNAL Split Panel pattern.
 * Owns the flex row, list-panel width (35%, min 280, max 420), border-right on
 * the list, and responsive stack behavior on mobile.
 *
 * @example
 *   <SplitPanel>
 *     <SplitPanel.List><GoalsListPanel ... /></SplitPanel.List>
 *     <SplitPanel.Detail><GoalDetailPanel ... /></SplitPanel.Detail>
 *   </SplitPanel>
 */
export default function SplitPanel({ children, className = '' }) {
    return <div className={`${styles.container} ${className}`}>{children}</div>;
}

SplitPanel.List = function SplitPanelList({ children, className = '' }) {
    return <div className={`${styles.list} ${className}`}>{children}</div>;
};

SplitPanel.Detail = function SplitPanelDetail({ children, className = '' }) {
    return <div className={`${styles.detail} ${className}`}>{children}</div>;
};
