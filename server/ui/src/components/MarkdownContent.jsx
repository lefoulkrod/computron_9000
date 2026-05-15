import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import remarkMath from 'remark-math';
import rehypeSanitize from 'rehype-sanitize';
import { defaultSchema } from 'rehype-sanitize';
import rehypeKatex from 'rehype-katex';
import rehypeMermaid from 'rehype-mermaid';
import remend from 'remend';
import 'katex/dist/katex.min.css';
import styles from './MarkdownContent.module.css';
import { PreCodeBlock, InlineCode } from './CodeBlock.jsx';

// Extend sanitize schema to allow KaTeX/MathML, Mermaid SVG, and preserve code language classes
const _sanitizeSchema = (() => {
    const extraTags = [
        'math', 'annotation', 'semantics',
        'mrow', 'mi', 'mo', 'mn', 'ms', 'mtext', 'mspace',
        'msup', 'msub', 'msubsup', 'mfrac', 'msqrt', 'mroot',
        'mstyle', 'merror', 'mpadded', 'mphantom', 'menclose',
        'munder', 'mover', 'munderover', 'mtable', 'mtr', 'mtd', 'annotation-xml',
        // Mermaid SVG elements
        'svg', 'g', 'defs', 'marker', 'path', 'line', 'rect', 'circle',
        'ellipse', 'polygon', 'polyline', 'text', 'tspan', 'foreignObject',
    ];
    return {
        ...defaultSchema,
        tagNames: Array.from(new Set([...(defaultSchema.tagNames || []), ...extraTags])),
        attributes: {
            ...(defaultSchema.attributes || {}),
            code: [...(((defaultSchema.attributes || {}).code) || []), 'className'],
            span: [...(((defaultSchema.attributes || {}).span) || []), 'className', 'style', 'aria-hidden'],
            math: [...(((defaultSchema.attributes || {}).math) || []), 'xmlns', 'display'],
            annotation: [...(((defaultSchema.attributes || {}).annotation) || []), 'encoding'],
            img: [...(((defaultSchema.attributes || {}).img) || []), 'src', 'alt', 'title'],
            // Mermaid SVG attributes
            svg: ['xmlns', 'viewBox', 'width', 'height', 'style', 'class', 'id', 'role', 'aria-roledescription'],
            g: ['class', 'transform', 'id'],
            path: ['d', 'fill', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin', 'class', 'id', 'marker-end', 'style'],
            line: ['x1', 'y1', 'x2', 'y2', 'stroke', 'stroke-width', 'stroke-linecap', 'class'],
            rect: ['x', 'y', 'width', 'height', 'fill', 'stroke', 'stroke-width', 'rx', 'ry', 'class'],
            circle: ['cx', 'cy', 'r', 'fill', 'stroke', 'stroke-width', 'class'],
            ellipse: ['cx', 'cy', 'rx', 'ry', 'fill', 'stroke', 'class'],
            polygon: ['points', 'fill', 'stroke', 'stroke-width', 'class'],
            polyline: ['points', 'fill', 'stroke', 'stroke-width', 'class', 'marker-end'],
            text: ['x', 'y', 'fill', 'font-family', 'font-size', 'font-weight', 'text-anchor', 'dominant-baseline', 'class', 'dy'],
            tspan: ['x', 'dy', 'fill', 'font-family', 'font-size', 'font-weight', 'class'],
            marker: ['id', 'viewBox', 'refX', 'refY', 'markerWidth', 'markerHeight', 'orient', 'class'],
            foreignObject: ['x', 'y', 'width', 'height'],
        },
        protocols: {
            ...(defaultSchema.protocols || {}),
            src: ['http', 'https', 'data']
        }
    };
})();

function _urlTransform(uri, key, node) {
    try {
        if (typeof uri !== 'string') return uri;
        if (node && node.tagName && node.tagName !== 'img') return uri;
        if (/^data:image\/svg\+xml/i.test(uri)) return undefined;
        if (/^data:image\/(png|jpe?g|gif|webp);base64,[a-z0-9+/=]+$/i.test(uri)) return uri;
        if (/^(javascript|vbscript|file|data:)/i.test(uri) && !uri.startsWith('data:image/')) return undefined;
        return uri;
    } catch (_e) {
        return undefined;
    }
}

function _normalizeMathDelimiters(md) {
    if (typeof md !== 'string' || md.length === 0) return '';
    md = md.replace(/\\\[([\s\S]*?)\\\]/g, (_m, inner) => `\n\n$$\n${inner}\n$$\n\n`);
    md = md.replace(/\\\((.+?)\\\)/g, (_m, inner) => `$${inner}$`);
    return md;
}

function _normalizeUnicode(md) {
    if (typeof md !== 'string' || md.length === 0) return '';
    md = md.replace(/[\u202F\u00A0\u2009]/g, ' ');
    md = md.replace(/\u2011/g, '-');
    return md;
}

function _escapeCurrencyDollars(md) {
    if (typeof md !== 'string' || md.length === 0) return '';
    return md.replace(/(?<!\\)\$(?=\d)/g, '\\$');
}

function _preprocessContent(md) {
    return _normalizeMathDelimiters(_normalizeUnicode(_escapeCurrencyDollars(md)));
}

const _markdownComponents = {
    pre: (props) => <PreCodeBlock {...props} />,
    code: (props) => <InlineCode {...props} />,
};

export default function MarkdownContent({ children, streaming }) {
    let content = _preprocessContent(children || '');
    if (streaming) content = remend(content);
    return (
        <div className={styles.markdown}>
            <ReactMarkdown
                urlTransform={_urlTransform}
                remarkPlugins={[remarkMath, remarkGfm, remarkBreaks]}
                rehypePlugins={[rehypeMermaid, [rehypeKatex, { strict: 'ignore' }], [rehypeSanitize, _sanitizeSchema]]}
                components={_markdownComponents}
            >
                {content}
            </ReactMarkdown>
        </div>
    );
}
