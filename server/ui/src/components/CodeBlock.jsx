import React, { useMemo, useState } from 'react';
import styles from './CodeBlock.module.css';
import CopyIcon from './icons/CopyIcon.jsx';
import copyToClipboard from '../utils/copyToClipboard.js';
import { highlightCode } from '../utils/highlight.js';

function CodeHeader({ lang, onCopy, copied }) {
  return (
    <div className={styles.codeblockHeader}>
      <span className={styles.codeblockLang}>{lang || 'code'}</span>
      <button className={styles.codeblockCopy} type="button" onClick={onCopy}>
        <CopyIcon size={12} />
        <span>{copied ? 'Copied!' : 'Copy code'}</span>
      </button>
    </div>
  );
}

// Inline code renderer — uses design language `.inline-code` pattern.
export function InlineCode({ className, children, ...props }) {
  const cls = className ? `${styles.inlineCode} ${className}` : styles.inlineCode;
  return (
    <code className={cls} data-testid="inline-code" {...props}>{children}</code>
  );
}

// Block code renderer — uses design language `.codeblock` pattern: an outer
// container with a normal-flow header above a `<pre>` body.
export function PreCodeBlock({ children }) {
  const [copied, setCopied] = useState(false);

  const { lang, text, codeEl } = useMemo(() => {
    let lang = 'code';
    let text = '';
    let codeEl = null;
    const arr = React.Children.toArray(children);
    for (const child of arr) {
      if (React.isValidElement(child)) {
        const cls = child.props?.className || '';
        const m = cls.match(/language-([a-zA-Z0-9+#._-]+)/);
        if (m) lang = m[1];
        const raw = child.props?.children;
        text = Array.isArray(raw) ? raw.join('') : String(raw ?? '');
        codeEl = child;
        break;
      }
    }
    return { lang, text, codeEl: codeEl ?? children };
  }, [children]);

  const highlighted = useMemo(() => {
    if (!text) return null;
    const requested = lang && lang !== 'code' ? lang : null;
    return highlightCode(text, { language: requested });
  }, [text, lang]);

  const handleCopy = async () => {
    const success = await copyToClipboard(text);
    if (!success) return;

    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={styles.codeblock} data-testid="code-block" data-lang={lang}>
      <CodeHeader lang={lang} onCopy={handleCopy} copied={copied} />
      <pre className={styles.codeblockBody}>
        {highlighted ? (
          <code
            className="hljs"
            dangerouslySetInnerHTML={{ __html: highlighted.html }}
          />
        ) : (
          codeEl
        )}
      </pre>
    </div>
  );
}

export default PreCodeBlock;
