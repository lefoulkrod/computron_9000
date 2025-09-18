import React, { useMemo, useState } from 'react';
import styles from './Message.module.css';
import CopyIcon from './icons/CopyIcon.jsx';
import copyToClipboard from '../utils/copyToClipboard.js';

function CodeHeader({ lang, onCopy, copied }) {
  return (
    <div className={styles.codeHeader}>
      <span className={styles.codeLangLabel}>{lang || 'code'}</span>
      <button className={styles.copyBtn} type="button" onClick={onCopy}>
        <CopyIcon size={16} />
        <span>{copied ? 'Copied!' : 'Copy code'}</span>
      </button>
    </div>
  );
}

// Inline code renderer: keep simple inline styling
export function InlineCode({ className, children, ...props }) {
  return (
    <code className={className} {...props}>{children}</code>
  );
}

// Block pre renderer: inject header and copy button while preserving children
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

  const handleCopy = async () => {
    const success = await copyToClipboard(text);
    if (!success) return;

    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <pre>
      <CodeHeader lang={lang} onCopy={handleCopy} copied={copied} />
      {codeEl}
    </pre>
  );
}

export default PreCodeBlock;
