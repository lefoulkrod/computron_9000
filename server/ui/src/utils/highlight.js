import hljs from 'highlight.js/lib/common';

const EXT_TO_LANG = {
    js: 'javascript',
    jsx: 'javascript',
    mjs: 'javascript',
    cjs: 'javascript',
    ts: 'typescript',
    tsx: 'typescript',
    py: 'python',
    rb: 'ruby',
    go: 'go',
    rs: 'rust',
    java: 'java',
    kt: 'kotlin',
    swift: 'swift',
    c: 'c',
    h: 'c',
    cpp: 'cpp',
    hpp: 'cpp',
    cc: 'cpp',
    cs: 'csharp',
    php: 'php',
    html: 'xml',
    htm: 'xml',
    xml: 'xml',
    svg: 'xml',
    css: 'css',
    scss: 'scss',
    less: 'less',
    json: 'json',
    yaml: 'yaml',
    yml: 'yaml',
    toml: 'ini',
    ini: 'ini',
    md: 'markdown',
    mdx: 'markdown',
    sh: 'bash',
    bash: 'bash',
    zsh: 'bash',
    sql: 'sql',
    dockerfile: 'dockerfile',
};

const CONTENT_TYPE_TO_LANG = {
    'application/javascript': 'javascript',
    'application/json': 'json',
    'application/xml': 'xml',
    'application/x-yaml': 'yaml',
    'text/css': 'css',
    'text/html': 'xml',
    'text/javascript': 'javascript',
    'text/markdown': 'markdown',
    'text/x-markdown': 'markdown',
    'text/x-python': 'python',
    'text/x-java': 'java',
    'text/x-c': 'c',
    'text/x-c++': 'cpp',
    'text/xml': 'xml',
    'text/yaml': 'yaml',
};

export function languageFromFilename(filename) {
    if (!filename) return null;
    const lower = filename.toLowerCase();
    if (lower === 'dockerfile' || lower.endsWith('/dockerfile')) return 'dockerfile';
    const m = filename.match(/\.([a-zA-Z0-9]+)$/);
    if (!m) return null;
    return EXT_TO_LANG[m[1].toLowerCase()] || null;
}

export function languageFromContentType(contentType) {
    if (!contentType) return null;
    return CONTENT_TYPE_TO_LANG[contentType.toLowerCase()] || null;
}

export function resolveLanguage({ language, filename, contentType } = {}) {
    if (language && hljs.getLanguage(language)) return language;
    const fromName = languageFromFilename(filename);
    if (fromName) return fromName;
    const fromType = languageFromContentType(contentType);
    if (fromType) return fromType;
    return null;
}

/**
 * Highlight a block of text. Always returns HTML-escaped output — hljs
 * escapes the input before wrapping tokens in spans, so the result is
 * safe to pass to dangerouslySetInnerHTML.
 */
export function highlightCode(text, { language, filename, contentType } = {}) {
    if (text == null) return { html: '', language: null };
    const lang = resolveLanguage({ language, filename, contentType });
    if (lang) {
        try {
            const res = hljs.highlight(text, { language: lang, ignoreIllegals: true });
            return { html: res.value, language: lang };
        } catch {
            // fall through to auto
        }
    }
    try {
        const res = hljs.highlightAuto(text);
        return { html: res.value, language: res.language || null };
    } catch {
        const escaped = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
        return { html: escaped, language: null };
    }
}
