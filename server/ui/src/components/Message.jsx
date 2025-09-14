import React, { useEffect, useRef, useState } from 'react';
import { marked } from 'marked';
import styles from './Message.module.css';

function useCodeCopyEnhancer(containerRef) {
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const pres = Array.from(container.querySelectorAll('pre > code'));
    pres.forEach((codeEl) => {
      const pre = codeEl.parentElement;
      if (!pre) return;
      // Avoid duplicate headers when re-rendering
      if (pre.querySelector(':scope > .code-header')) return;

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
      copyBtn.textContent = 'Copy';
      copyBtn.addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(codeEl.textContent || '');
          const prev = copyBtn.textContent;
          copyBtn.textContent = 'Copied!';
          setTimeout(() => (copyBtn.textContent = prev), 1200);
        } catch (_e) {
          // no-op
        }
      });

      header.appendChild(langLabel);
      header.appendChild(copyBtn);
      // Insert header inside the <pre> so it appears within the code area
      pre.insertBefore(header, pre.firstChild);
    });

    return () => {
      // Cleanup listeners if any (optional)
      const headers = Array.from(container.querySelectorAll('.code-header .copy-btn'));
      headers.forEach((btn) => {
        const clone = btn.cloneNode(true);
        btn.parentNode?.replaceChild(clone, btn);
      });
    };
  }, [containerRef]);
}

function AssistantMessage({ content, thinking, images, placeholder }) {
  const [expanded, setExpanded] = useState(false);
  const bubbleRef = useRef(null);
  useCodeCopyEnhancer(bubbleRef);
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
              {expanded ? 'Hide thoughts' : 'Show thoughts'}
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
  useCodeCopyEnhancer(bubbleRef);
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
