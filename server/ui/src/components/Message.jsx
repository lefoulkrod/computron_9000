import { useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import remarkMath from 'remark-math';
import rehypeSanitize from 'rehype-sanitize';
import { defaultSchema } from 'rehype-sanitize';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import styles from './Message.module.css';
import ThinkingIcon from './icons/ThinkingIcon.jsx';
import ChevronIcon from './icons/ChevronIcon.jsx';
import { PreCodeBlock, InlineCode } from './CodeBlock.jsx';
import ToolCallsSummary from './ToolCallsSummary';


// Extend sanitize schema to allow KaTeX/MathML output and preserve code language classes
const sanitizeSchema = (() => {
    const extraTags = [
        'math', 'annotation', 'semantics',
        'mrow', 'mi', 'mo', 'mn', 'ms', 'mtext', 'mspace',
        'msup', 'msub', 'msubsup', 'mfrac', 'msqrt', 'mroot',
        'mstyle', 'merror', 'mpadded', 'mphantom', 'menclose',
        'munder', 'mover', 'munderover', 'mtable', 'mtr', 'mtd', 'annotation-xml'
    ];
    return {
        ...defaultSchema,
        tagNames: Array.from(new Set([...(defaultSchema.tagNames || []), ...extraTags])),
        attributes: {
            ...(defaultSchema.attributes || {}),
            code: [
                ...(((defaultSchema.attributes || {}).code) || []),
                'className'
            ],
            span: [
                ...(((defaultSchema.attributes || {}).span) || []),
                'className', 'style', 'aria-hidden'
            ],
            math: [
                ...(((defaultSchema.attributes || {}).math) || []),
                'xmlns', 'display'
            ],
            annotation: [
                ...(((defaultSchema.attributes || {}).annotation) || []),
                'encoding'
            ],
            // Allow images; we specifically permit data: URIs in transformImageUri below.
            img: [
                ...(((defaultSchema.attributes || {}).img) || []),
                'src', 'alt', 'title'
            ]
        },
        // Extend allowed protocols so rehype-sanitize does not strip data:image/* that we approve.
        protocols: {
            ...(defaultSchema.protocols || {}),
            src: ['http', 'https', 'data']
        }
    };
})();

// Allow data: image/* URIs while still blocking javascript: etc. For other URLs, fall back to default behavior.
function _urlTransform(uri, key, node) {
    // SECURITY NOTES:
    // We explicitly allow base64-encoded image data URLs so the model/user can inline small
    // screenshots or generated images directly inside markdown. We restrict the accepted
    // pattern to a conservative whitelist of common raster formats plus SVG (xml) and ensure
    // it is base64 data only (no arbitrary inline scripts). We additionally reject other
    // potentially dangerous schemes (javascript:, vbscript:, file:, generic data: not starting
    // with data:image/). If the URI does not match, we return an empty string which causes
    // react-markdown to render nothing for that src, avoiding accidental execution contexts.
    try {
        if (typeof uri !== 'string') return uri;
        // Only apply special handling for image nodes
        if (node && node.tagName && node.tagName !== 'img') return uri;
        // Permit data URL images (PNG, JPEG, GIF, SVG, WebP) - basic validation
        // Block inline SVG (potential for script execution via onload, animation, etc.)
        if (/^data:image\/svg\+xml/i.test(uri)) {
            return undefined;
        }
        if (/^data:image\/(png|jpe?g|gif|webp);base64,[a-z0-9+/=]+$/i.test(uri)) {
            return uri;
        }
        // Block obviously dangerous schemes
        if (/^(javascript|vbscript|file|data:)/i.test(uri) && !uri.startsWith('data:image/')) {
            // Returning undefined signals react-markdown not to set the attribute.
            return undefined;
        }
        return uri;
    } catch (_e) {
        return undefined;
    }
}

// Support KaTeX bracket delimiters by normalizing to $ ... $ and $$ ... $$
function normalizeMathDelimiters(md) {
    if (typeof md !== 'string' || md.length === 0) return '';
    // Block math: \[ ... \] (allowing newlines inside)
    md = md.replace(/\\\[([\s\S]*?)\\\]/g, (_m, inner) => `\n\n$$\n${inner}\n$$\n\n`);
    // Inline math: \( ... \) (no newlines preferred)
    md = md.replace(/\\\((.+?)\\\)/g, (_m, inner) => `$${inner}$`);
    return md;
}

// Normalize unicode spaces/hyphens that KaTeX warns about
function normalizeUnicode(md) {
    if (typeof md !== 'string' || md.length === 0) return '';
    // Replace narrow no-break space, NBSP, thin space with regular space
    md = md.replace(/[\u202F\u00A0\u2009]/g, ' ');
    // Replace non-breaking hyphen with standard hyphen-minus
    md = md.replace(/\u2011/g, '-');
    return md;
}

function preprocessContent(md) {
    return normalizeMathDelimiters(normalizeUnicode(md));
}

const markdownComponents = {
    pre: (props) => <PreCodeBlock {...props} />,
    code: (props) => <InlineCode {...props} />,
};

function MarkdownContent({ children }) {
    return (
        <ReactMarkdown
            urlTransform={_urlTransform}
            remarkPlugins={[remarkMath, remarkGfm, remarkBreaks]}
            rehypePlugins={[[rehypeKatex, { strict: 'ignore' }], [rehypeSanitize, sanitizeSchema]]}
            components={markdownComponents}
        >
            {preprocessContent(children || '')}
        </ReactMarkdown>
    );
}

// Format agent name for display
function formatAgentName(agentName) {
    if (!agentName) return 'COMPUTRON_9000';

    // Convert snake_case to Title Case
    return agentName
        .split('_')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
}



function AssistantMessage({ content, thinking, images, placeholder, agent_name, depth = 0, data }) {
    const [thinkingExpanded, setThinkingExpanded] = useState(false);
    const bubbleRef = useRef(null);
    const displayName = formatAgentName(agent_name);

    const toolCalls = Array.isArray(data)
        ? data.filter(item => item && item.type === 'tool_call')
        : [];

    return (
        <div
            className={`${styles.message} ${styles.assistant} ${depth > 0 ? styles.subAgent : ''}`}
            style={{ '--depth-level': depth }}
        >
            <div className={styles.bubble} ref={bubbleRef}>
                {!placeholder && (agent_name || toolCalls.length > 0) && (
                    <div className={styles.messageHeader}>
                        {agent_name && (
                            <span className={styles.agentLabel}>
                                {depth > 0 && '↳ '}{displayName}
                            </span>
                        )}
                        {agent_name && toolCalls.length > 0 && ' — '}
                        <ToolCallsSummary toolCalls={toolCalls} />
                    </div>
                )}
                {placeholder && (
                    <div className={styles.loadingIndicator}>
                        Thinking<span className={styles.dot}>.</span>
                        <span className={styles.dot}>.</span>
                        <span className={styles.dot}>.</span>
                    </div>
                )}
                {!placeholder && thinking && (
                    <div
                        className={`${styles.collapsibleThink} ${thinkingExpanded ? styles.expanded : ''}`}
                    >
                        <div
                            className={styles.collapsibleThinkHeader}
                            onClick={() => setThinkingExpanded((e) => !e)}
                        >
                            <span className={styles.thinkIcon} aria-hidden="true">
                                <ThinkingIcon size={18} />
                            </span>
                            <span>{thinkingExpanded ? 'Hide thoughts' : 'Show thoughts'}</span>
                            <ChevronIcon size={12} direction={thinkingExpanded ? 'up' : 'down'} />
                        </div>
                        {thinkingExpanded && (
                            <div className={styles.collapsibleThinkContent}>
                                <MarkdownContent>{thinking}</MarkdownContent>
                            </div>
                        )}
                    </div>
                )}
                {!placeholder && <MarkdownContent>{content}</MarkdownContent>}
                {Array.isArray(images) && images.length > 0 && (
                    <div className={styles.messageImages}>
                        {images.map((src, i) => (
                            <img key={i} src={src} alt={`assistant-attachment-${i}`} />
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

function UserMessage({ content, images }) {
    return (
        <div className={`${styles.message} ${styles.user}`}>
            <div className={styles.bubble}>
                <MarkdownContent>{content}</MarkdownContent>
                {Array.isArray(images) && images.length > 0 && (
                    <div className={styles.messageImages}>
                        {images.map((src, i) => (
                            <img key={i} src={src} alt={`user-attachment-${i}`} />
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

export default function Message(props) {
    return props.role === 'assistant' ? (
        <AssistantMessage {...props} />
    ) : (
        <UserMessage {...props} />
    );
}
