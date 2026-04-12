import { useState, useEffect, useCallback } from 'react';

/**
 * Agent profiles hook. Fetches profiles on mount and provides
 * CRUD operations plus duplicate via the backend API.
 */
export default function useAgentProfiles() {
    const [profiles, setProfiles] = useState([]);
    const [selectedProfileId, setSelectedProfileId] = useState(null);
    const [loading, setLoading] = useState(true);
    const [revision, setRevision] = useState(0);

    const refresh = useCallback(async () => {
        setLoading(true);
        try {
            const res = await fetch('/api/profiles');
            const data = await res.json();
            setProfiles(data);
            // Auto-select first profile if nothing selected
            if (data.length > 0) {
                setSelectedProfileId((prev) => prev || data[0].id);
            }
        } catch {
            // keep current state on error
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        refresh();
    }, [refresh]);

    const createProfile = useCallback(async (profile) => {
        const res = await fetch('/api/profiles', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(profile),
        });
        const created = await res.json();
        setProfiles(prev => [...prev, created]);
        setRevision(r => r + 1);
        return created;
    }, []);

    const updateProfile = useCallback(async (id, profile) => {
        const res = await fetch(`/api/profiles/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(profile),
        });
        const updated = await res.json();
        setProfiles(prev => prev.map(p => p.id === id ? updated : p));
        setRevision(r => r + 1);
        return updated;
    }, []);

    const deleteProfile = useCallback(async (id) => {
        const res = await fetch(`/api/profiles/${id}`, { method: 'DELETE' });
        if (res.status === 409) {
            const data = await res.json();
            return { conflict: true, ...data };
        }
        setProfiles(prev => prev.filter(p => p.id !== id));
        if (selectedProfileId === id) setSelectedProfileId(null);
        setRevision(r => r + 1);
        return { conflict: false };
    }, [selectedProfileId]);

    const duplicateProfile = useCallback(async (id) => {
        const res = await fetch(`/api/profiles/${id}/duplicate`, { method: 'POST' });
        const duplicated = await res.json();
        setProfiles(prev => [...prev, duplicated]);
        setRevision(r => r + 1);
        return duplicated;
    }, []);

    return {
        profiles,
        selectedProfileId,
        setSelectedProfileId,
        createProfile,
        updateProfile,
        deleteProfile,
        duplicateProfile,
        loading,
        refresh,
        revision,
    };
}
