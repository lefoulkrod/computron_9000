const _CSRF_SAFE = new Set(['GET', 'HEAD']);

/**
 * Drop-in replacement for fetch() that automatically adds the CSRF header
 * required by the server on all mutating requests (POST, PUT, DELETE, etc.).
 */
export function apiFetch(input, init = {}) {
    const method = (init.method || 'GET').toUpperCase();
    const headers = _CSRF_SAFE.has(method)
        ? init.headers
        : { 'X-Requested-With': 'XMLHttpRequest', ...init.headers };
    return fetch(input, { ...init, headers });
}
