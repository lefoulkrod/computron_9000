import React, { useState, useEffect } from 'react';
import Header from './components/Header.jsx';
import ChatInput from './components/ChatInput.jsx';
import ChatMessages from './components/ChatMessages.jsx';

function App() {
  const [messages, setMessages] = useState([]);
  const [dark, setDark] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);

  useEffect(() => {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    setDark(prefersDark);
  }, []);

  useEffect(() => {
    document.body.classList.toggle('dark-theme', dark);
  }, [dark]);

  const toggleTheme = () => setDark((d) => !d);

  const newSession = async () => {
    setMessages([]);
    try {
      await fetch('/api/chat/history', { method: 'DELETE' });
    } catch (err) {
      // ignore
    }
  };

  const sendMessage = async (message, fileData) => {
    // Allow sending if there's text or a file
    if (!message && !fileData) return;

    // Build user message with optional image preview
    const userMsg = { role: 'user', content: message || '' };
    if (fileData && fileData.content_type && fileData.content_type.startsWith('image/')) {
      userMsg.images = [`data:${fileData.content_type};base64,${fileData.base64}`];
    }
    const placeholderId = Math.random().toString(36).slice(2);
    setMessages((prev) => [
      ...prev,
      userMsg,
      { role: 'assistant', placeholder: true, tempId: placeholderId },
    ]);

    const body = { message: message || '(uploaded file)' };
    if (fileData) {
      body.data = [fileData];
    }
    try {
      setIsStreaming(true);
      const resp = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.body) return;
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let hasAssistant = false;
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buffer.indexOf('\n')) !== -1) {
          const line = buffer.slice(0, idx).trim();
          buffer = buffer.slice(idx + 1);
          if (!line) continue;
          try {
            const data = JSON.parse(line);
            setMessages((prev) => {
              const updated = [...prev];
              // First chunk: replace placeholder with the assistant message
              if (!hasAssistant) {
                hasAssistant = true;
                const pIndex = updated.findIndex((m) => m.placeholder && m.tempId === placeholderId);
                const assistantMsg = {
                  role: 'assistant',
                  content: data.response || '',
                  thinking: data.thinking,
                  streaming: !data.final,
                };
                if (pIndex !== -1) {
                  updated[pIndex] = assistantMsg;
                } else {
                  updated.push(assistantMsg);
                }
                return updated;
              }
              // Subsequent chunks: append to the last assistant message
              for (let i = updated.length - 1; i >= 0; i--) {
                if (updated[i].role === 'assistant') {
                  updated[i] = {
                    ...updated[i],
                    content: (updated[i].content || '') + (data.response || ''),
                    thinking: data.thinking,
                    streaming: !data.final,
                  };
                  break;
                }
              }
              return updated;
            });
          } catch (e) {
            // ignore parse errors for partial/incomplete lines
          }
        }
      }
    } catch (err) {
      // Replace placeholder with error, if present
      setMessages((prev) => {
        const updated = [...prev];
        const pIndex = updated.findIndex((m) => m.placeholder);
        if (pIndex !== -1) {
          updated[pIndex] = { role: 'assistant', content: `[Error: ${err.message}]` };
          return updated;
        }
        return [...prev, { role: 'assistant', content: `[Error: ${err.message}]` }];
      });
    } finally {
      setIsStreaming(false);
    }
  };

  return (
    <>
      <Header dark={dark} onToggleTheme={toggleTheme} onNewSession={newSession} />
      <div className="main-layout">
        <div className="column">
          <ChatInput onSend={sendMessage} disabled={isStreaming} />
        </div>
        <div className="column">
          <ChatMessages messages={messages} />
        </div>
      </div>
    </>
  );
}

export default App;
