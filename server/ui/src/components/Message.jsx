import React, { useEffect, useRef, useState } from 'react';
import { marked } from 'marked';
import styles from './Message.module.css';
import LightbulbIcon from './icons/LightbulbIcon.jsx';

function useCodeCopyEnhancer(containerRef, deps = []) {
    useEffect(() => {
        const container = containerRef.current;
        if (!container) return;

        const pres = Array.from(container.querySelectorAll('pre > code'));
        pres.forEach((codeEl) => {
            const pre = codeEl.parentElement;
            if (!pre) return;
            // If we've already enhanced this <pre>, skip
            if (pre.dataset.enhanced === 'true') return;
            // Defensive: remove any extra duplicate headers
            const existing = pre.querySelectorAll(`:scope > .${styles.codeHeader}`);
            if (existing.length > 1) {
                existing.forEach((h, i) => i > 0 && h.remove());
            }

            const header = document.createElement('div');
            header.className = styles.codeHeader;

            const langLabel = document.createElement('span');
            langLabel.className = styles.codeLangLabel;
            const cls = codeEl.className || '';
            const match = cls.match(/language-([a-zA-Z0-9+#._-]+)/);
            langLabel.textContent = match ? match[1] : 'code';

            const copyBtn = document.createElement('button');
            copyBtn.className = styles.copyBtn;
            copyBtn.type = 'button';
            // Build a dedicated SVG icon (same geometry as CopyIcon component)
            const svgNS = 'http://www.w3.org/2000/svg';
            const svg = document.createElementNS(svgNS, 'svg');
            svg.setAttribute('viewBox', '0 0 24 24');
            svg.setAttribute('width', '16');
            svg.setAttribute('height', '16');
            svg.style.display = 'block';
            const r1 = document.createElementNS(svgNS, 'rect');
            r1.setAttribute('x', '9'); r1.setAttribute('y', '9'); r1.setAttribute('width', '11'); r1.setAttribute('height', '11');
            r1.setAttribute('rx', '2'); r1.setAttribute('ry', '2');
            r1.setAttribute('stroke', 'currentColor'); r1.setAttribute('stroke-width', '1.8'); r1.setAttribute('fill', 'none');
            const r2 = document.createElementNS(svgNS, 'rect');
            r2.setAttribute('x', '4'); r2.setAttribute('y', '4'); r2.setAttribute('width', '11'); r2.setAttribute('height', '11');
            r2.setAttribute('rx', '2'); r2.setAttribute('ry', '2');
            r2.setAttribute('stroke', 'currentColor'); r2.setAttribute('stroke-width', '1.8'); r2.setAttribute('fill', 'none');
            svg.appendChild(r1); svg.appendChild(r2);
            const label = document.createElement('span');
            label.textContent = 'Copy code';
            copyBtn.appendChild(svg);
            copyBtn.appendChild(label);
            copyBtn.addEventListener('click', async () => {
                try {
                    await navigator.clipboard.writeText(codeEl.textContent || '');
                    const prevText = label.textContent;
                    label.textContent = 'Copied!';
                    setTimeout(() => (label.textContent = prevText), 2200);
                } catch (_e) {
                    // no-op
                }
            });

            header.appendChild(langLabel);
            header.appendChild(copyBtn);
            // Insert header inside the <pre> so it appears within the code area
            pre.insertBefore(header, pre.firstChild);
            pre.dataset.enhanced = 'true';
        });

        // No special cleanup required; elements are recreated with content updates
    }, [containerRef, ...deps]);
}

function AssistantMessage({ content, thinking, images, placeholder }) {
    const [expanded, setExpanded] = useState(false);
    const bubbleRef = useRef(null);
    useCodeCopyEnhancer(bubbleRef, [content]);
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
                            <div
                                className={styles.collapsibleThinkContent}
                                dangerouslySetInnerHTML={{ __html: thinking.replace(/\n/g, '<br/>') }}
                            />
                        )}
                    </div>
                )}
                {!placeholder && (
                    <div dangerouslySetInnerHTML={{ __html: marked.parse(content || '') }} />
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
    useCodeCopyEnhancer(bubbleRef, [content]);
    return (
        <div className={`${styles.message} ${styles.user}`}>
            <div className={styles.bubble} ref={bubbleRef}>
                {content}
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
