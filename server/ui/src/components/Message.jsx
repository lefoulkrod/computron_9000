import React, { useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import remarkMath from 'remark-math';
import rehypeSanitize from 'rehype-sanitize';
import { defaultSchema } from 'rehype-sanitize';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import styles from './Message.module.css';
import LightbulbIcon from './icons/LightbulbIcon.jsx';
import { PreCodeBlock, InlineCode } from './CodeBlock.jsx';
 

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
            ]
        }
    };
})();

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

function AssistantMessage({ content, thinking, images, placeholder }) {
    const [expanded, setExpanded] = useState(false);
    const bubbleRef = useRef(null);
    return (
        <div className={`${styles.message} ${styles.assistant}`}>
            <div className={styles.bubble} ref={bubbleRef}>
                {placeholder && (
                    <div className={styles.loadingIndicator}>
                        Thinking<span className={styles.dot}>.</span>
                        <span className={styles.dot}>.</span>
                        <span className={styles.dot}>.</span>
                    </div>
                )}
                {!placeholder && thinking && (
                    <div
                        className={`${styles.collapsibleThink} ${expanded ? styles.expanded : ''}`}
                    >
                        <div
                            className={styles.collapsibleThinkHeader}
                            onClick={() => setExpanded((e) => !e)}
                        >
                            <span className={styles.thinkIcon} aria-hidden="true">
                                <LightbulbIcon size={18} />
                            </span>
                            <span>{expanded ? 'Hide thoughts' : 'Show thoughts'}</span>
                        </div>
                        {expanded && (
                            <div className={styles.collapsibleThinkContent}>
                                <ReactMarkdown
                                    remarkPlugins={[remarkMath, remarkGfm, remarkBreaks]}
                                    rehypePlugins={[[rehypeKatex, { strict: 'ignore' }], [rehypeSanitize, sanitizeSchema]]}
                                    components={{
                                        pre: (props) => <PreCodeBlock {...props} />,
                                        code: (props) => <InlineCode {...props} />,
                                    }}
                                >
                                    {preprocessContent(thinking || '')}
                                </ReactMarkdown>
                            </div>
                        )}
                    </div>
                )}
                {!placeholder && (
                    <ReactMarkdown
                        remarkPlugins={[remarkMath, remarkGfm, remarkBreaks]}
                        rehypePlugins={[[rehypeKatex, { strict: 'ignore' }], [rehypeSanitize, sanitizeSchema]]}
                        components={{
                            pre: (props) => <PreCodeBlock {...props} />,
                            code: (props) => <InlineCode {...props} />,
                        }}
                    >
                        {preprocessContent(content || '')}
                    </ReactMarkdown>
                )}
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
    const bubbleRef = useRef(null);
    return (
        <div className={`${styles.message} ${styles.user}`}>
            <div className={styles.bubble} ref={bubbleRef}>
                <ReactMarkdown
                    remarkPlugins={[remarkMath, remarkGfm, remarkBreaks]}
                    rehypePlugins={[[rehypeKatex, { strict: 'ignore' }], [rehypeSanitize, sanitizeSchema]]}
                    components={{
                        pre: (props) => <PreCodeBlock {...props} />,
                        code: (props) => <InlineCode {...props} />,
                    }}
                >
                    {preprocessContent(content || '')}
                </ReactMarkdown>
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
