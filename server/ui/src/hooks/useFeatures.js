import { useState, useEffect } from 'react';

const DEFAULTS = {
    image_generation: false,
    music_generation: false,
    desktop: false,
    visual_grounding: false,
};

/**
 * Fetch feature flags from the server once on mount.
 * Returns the flags object (defaults to all-false until loaded).
 */
export default function useFeatures() {
    const [features, setFeatures] = useState(DEFAULTS);

    useEffect(() => {
        fetch('/api/features')
            .then((res) => res.json())
            .then(setFeatures)
            .catch(() => {}); // keep defaults on error
    }, []);

    return features;
}
