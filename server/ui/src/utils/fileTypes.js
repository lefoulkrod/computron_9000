/**
 * Checks if a file can be previewed in the preview panel.
 * If false, the file should be downloaded instead.
 */
export function canPreviewFile(contentType, filename) {
    if (!contentType && !filename) return false;

    // Images
    if (contentType?.startsWith('image/')) return true;
    if (filename?.match(/\.(jpg|jpeg|png|gif|webp|svg|ico|bmp)$/i)) return true;

    // PDF
    if (contentType === 'application/pdf') return true;
    if (filename?.match(/\.pdf$/i)) return true;

    // HTML
    if (contentType === 'text/html') return true;
    if (filename?.match(/\.(html|htm)$/i)) return true;

    // Any text type
    if (contentType?.startsWith('text/')) return true;

    // Code/config files (may have application/* content types)
    if (contentType === 'application/json' || contentType === 'application/xml') return true;
    if (filename?.match(/\.(js|jsx|ts|tsx|py|java|cpp|c|h|go|rs|rb|php|css|json|xml|yaml|yml|md|mdx|txt|csv|log|sh|bash|zsh|sql|toml|ini|cfg|env|dockerfile|makefile|gitignore|editorconfig|prettierrc|eslintrc)$/i)) return true;

    // Everything else: not previewable (download instead)
    return false;
}

/**
 * Checks if the file has a source/preview toggle (markdown or HTML).
 */
export function hasPreviewToggle(contentType, filename) {
    if (contentType === 'text/markdown' || contentType === 'text/x-markdown') return true;
    if (contentType === 'text/html') return true;
    if (filename?.endsWith('.md') || filename?.endsWith('.mdx')) return true;
    if (filename?.endsWith('.html') || filename?.endsWith('.htm')) return true;
    return false;
}

/**
 * Checks if a file is an image.
 */
export function isImageFile(contentType, filename) {
    if (contentType?.startsWith('image/')) return true;
    if (filename?.match(/\.(jpg|jpeg|png|gif|webp|svg|ico|bmp)$/i)) return true;
    return false;
}

/**
 * Checks if a file is a PDF.
 */
export function isPdfFile(contentType, filename) {
    if (contentType === 'application/pdf') return true;
    if (filename?.match(/\.pdf$/i)) return true;
    return false;
}
