export async function copyToClipboard(text) {
  if (typeof text !== 'string') {
    return false;
  }

  const write = async () => {
    const clip = typeof navigator !== 'undefined' ? navigator.clipboard : undefined;
    if (clip && typeof clip.writeText === 'function') {
      await clip.writeText(text);
      return true;
    }
    return false;
  };

  const fallback = () => {
    if (typeof document === 'undefined' || !document.body) {
      return false;
    }
    try {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.setAttribute('readonly', '');
      textarea.style.position = 'absolute';
      textarea.style.left = '-9999px';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      return true;
    } catch (_error) {
      return false;
    }
  };

  try {
    const copied = await write();
    if (copied) return true;
    return fallback();
  } catch (_error) {
    return fallback();
  }
}

export default copyToClipboard;
