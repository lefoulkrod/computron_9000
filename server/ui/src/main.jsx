import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import { ToastProvider } from './components/ToastProvider.jsx';
import './global.css';
import './hljs-tokens.css';

// Patch fetch globally so mutating requests always carry the CSRF header.
// The server requires X-Requested-With: XMLHttpRequest on POST/PUT/DELETE.
// Same-origin JS can set this freely; cross-origin JS cannot because the
// server does not list it in Access-Control-Allow-Headers.
const _originalFetch = window.fetch;
window.fetch = (input, init = {}) => {
    const method = (init.method || 'GET').toUpperCase();
    if (method !== 'GET' && method !== 'HEAD') {
        init = { ...init, headers: { 'X-Requested-With': 'XMLHttpRequest', ...init.headers } };
    }
    return _originalFetch(input, init);
};

ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
        <ToastProvider>
            <App />
        </ToastProvider>
    </React.StrictMode>
);
