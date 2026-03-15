import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * Shared hook for sidebar list panels that fetch, refresh, collapse,
 * delete items, and optionally highlight newly-added items.
 *
 * @param {string} endpoint - API endpoint to GET items from
 * @param {object} options
 * @param {number} [options.refreshSignal] - Increment to trigger a re-fetch
 * @param {function} [options.getId] - Extract unique id from an item (default: item => item.id)
 * @param {function} [options.transform] - Transform the JSON response into the items array
 * @param {boolean} [options.startCollapsed] - Whether panel starts collapsed (default: false)
 */
export default function useListPanel(endpoint, {
    refreshSignal = 0,
    getId = (item) => item.id,
    transform = (data) => data,
    onFetched = null,
    startCollapsed = false,
} = {}) {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [collapsed, setCollapsed] = useState(startCollapsed);
    const [deleting, setDeleting] = useState(null);
    const [newItemIds, setNewItemIds] = useState(new Set());
    const prevIdsRef = useRef(new Set());

    const fetchItems = useCallback(async () => {
        try {
            const resp = await fetch(endpoint);
            if (resp.ok) {
                const data = await resp.json();
                const fresh = transform(data);
                const freshIds = new Set(fresh.map(getId));
                const added = fresh.filter((item) => !prevIdsRef.current.has(getId(item))).map(getId);
                prevIdsRef.current = freshIds;
                if (added.length > 0) {
                    setNewItemIds(new Set(added));
                    setTimeout(() => setNewItemIds(new Set()), 700);
                }
                setItems(fresh);
                if (onFetched) onFetched(data);
            }
        } catch (_) {
            // ignore
        } finally {
            setLoading(false);
        }
    }, [endpoint, getId, transform, onFetched]);

    useEffect(() => { fetchItems(); }, [fetchItems]);
    useEffect(() => { if (refreshSignal > 0) fetchItems(); }, [refreshSignal, fetchItems]);

    const handleDelete = useCallback(async (key, deleteEndpoint, matchFn) => {
        setDeleting(key);
        try {
            const resp = await fetch(deleteEndpoint, { method: 'DELETE' });
            if (resp.ok || resp.status === 404) {
                setItems((prev) => prev.filter(matchFn));
            }
        } catch (_) {
            // ignore
        } finally {
            setDeleting(null);
        }
    }, []);

    return {
        items,
        setItems,
        loading,
        collapsed,
        setCollapsed,
        deleting,
        handleDelete,
        newItemIds,
        refetch: fetchItems,
    };
}
