import styles from './ProfileList.module.css';

function Badge({ className, children }) {
    return <span className={`${styles.badge} ${className}`}>{children}</span>;
}

function ProfileItem({ profile, selected, onSelect }) {
    const { id, name, description, skills, temperature, think, enabled } = profile;
    const isDisabled = enabled === false;

    return (
        <li
            className={`${styles.item} ${selected ? styles.itemActive : ''} ${isDisabled ? styles.itemDisabled : ''}`}
            onClick={() => onSelect(id)}
            role="button"
            tabIndex={0}
            data-testid={`profile-item-${id}`}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(id); } }}
        >
            <div className={styles.itemBody}>
                <span className={styles.name}>{name}</span>
                {description && (
                    <span className={styles.desc}>{description}</span>
                )}
                <div className={styles.badges}>
                    {isDisabled && (
                        <Badge className={styles.badgeDisabled}>disabled</Badge>
                    )}
                    {(skills || []).map(skill => (
                        <Badge key={skill} className={styles.badgeSkill}>{skill}</Badge>
                    ))}
                    {temperature != null && (
                        <Badge className={styles.badgeParam}>{temperature} temp</Badge>
                    )}
                    {think && (
                        <Badge className={styles.badgeParam}>think</Badge>
                    )}
                </div>
            </div>
        </li>
    );
}

export default function ProfileList({ profiles, selectedId, onSelect, onNew }) {
    return (
        <div className={styles.panel}>
            <div className={styles.header}>
                <span className={styles.headerLabel}>Profiles</span>
                <button className={styles.newBtn} onClick={onNew}>+ New</button>
            </div>

            <div className={styles.list}>
                {profiles.map(profile => (
                    <ProfileItem
                        key={profile.id}
                        profile={profile}
                        selected={selectedId === profile.id}
                        onSelect={onSelect}
                    />
                ))}
            </div>
        </div>
    );
}
