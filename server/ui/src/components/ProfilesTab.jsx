import { useState, useEffect } from 'react';

import ProfileList from './ProfileList.jsx';
import ProfileBuilder from './ProfileBuilder.jsx';

export default function ProfilesTab({ profilesHook, features }) {
    const [allModels, setAllModels] = useState([]);
    const [draftProfile, setDraftProfile] = useState(null);
    const [deleteConflict, setDeleteConflict] = useState(null);

    useEffect(() => {
        fetch('/api/models').then(r => r.json()).then(data => {
            setAllModels(data.models || []);
        }).catch(() => {});
    }, []);

    // Drop any stale conflict when the user switches profiles.
    useEffect(() => {
        setDeleteConflict(null);
    }, [profilesHook.selectedProfileId, draftProfile]);

    const availableSkills = [
        'coder', 'browser', 'goal_planner',
        ...(features.desktop ? ['desktop'] : []),
        ...(features.image_generation ? ['image_gen'] : []),
        ...(features.music_generation ? ['music_gen'] : []),
    ];

    const selectedProfile = draftProfile
        ?? profilesHook.profiles.find(p => p.id === profilesHook.selectedProfileId)
        ?? null;

    return (
        <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
            <ProfileList
                profiles={profilesHook.profiles}
                selectedId={draftProfile ? null : profilesHook.selectedProfileId}
                onSelect={(id) => {
                    setDraftProfile(null);
                    profilesHook.setSelectedProfileId(id);
                }}
                onNew={() => {
                    setDraftProfile({
                        id: `custom_${Date.now()}`,
                        name: 'New Profile',
                        description: '',
                        icon: '🤖',
                        model: allModels[0]?.name || '',
                        system_prompt: '',
                        skills: [],
                        _unsaved: true,
                    });
                }}
            />
            <ProfileBuilder
                profile={selectedProfile}
                onSave={async (updated) => {
                    if (updated._unsaved) {
                        const { _unsaved, ...payload } = updated;
                        const created = await profilesHook.createProfile(payload);
                        if (created) {
                            setDraftProfile(null);
                            profilesHook.setSelectedProfileId(created.id);
                        }
                        return { ok: true, data: created };
                    }
                    return profilesHook.updateProfile(updated.id, updated);
                }}
                onDelete={async (id) => {
                    if (draftProfile && draftProfile.id === id) {
                        setDraftProfile(null);
                        setDeleteConflict(null);
                        return;
                    }
                    const result = await profilesHook.deleteProfile(id);
                    setDeleteConflict(result?.conflict ? result : null);
                }}
                deleteConflict={deleteConflict}
                onDismissDeleteConflict={() => setDeleteConflict(null)}
                onDuplicate={async (id) => {
                    if (draftProfile && draftProfile.id === id) return;
                    const result = await profilesHook.duplicateProfile(id);
                    if (result) profilesHook.setSelectedProfileId(result.id);
                }}
                models={allModels}
                availableSkills={availableSkills}
            />
        </div>
    );
}
