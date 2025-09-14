import React, { useState, useEffect } from 'react';
import Header from './components/Header.jsx';
import ChatInput from './components/ChatInput.jsx';
import ChatMessages from './components/ChatMessages.jsx';
import styles from './App.module.css';

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
        const userMsg = { id: `u_${Date.now()}_${Math.random().toString(36).slice(2)}`, role: 'user', content: message || '' };
        if (fileData && fileData.content_type && fileData.content_type.startsWith('image/')) {
            userMsg.images = [`data:${fileData.content_type};base64,${fileData.base64}`];
        }
        const placeholderId = Math.random().toString(36).slice(2);
        setMessages((prev) => [
            ...prev,
            userMsg,
            { id: placeholderId, role: 'assistant', placeholder: true, tempId: placeholderId },
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
                            // Find any existing assistant message for this request
                            let idx = updated.findIndex(
                                (m) => m.role === 'assistant' && (m.id === placeholderId || m.tempId === placeholderId)
                            );
                            if (idx === -1) {
                                // No placeholder found yet (race), create a new assistant message entry
                                updated.push({ id: placeholderId, role: 'assistant', content: '', thinking: undefined, streaming: true });
                                idx = updated.length - 1;
                            }
                            const current = updated[idx];
                            const next = {
                                ...current,
                                id: placeholderId,
                                placeholder: false,
                                tempId: undefined,
                                content: (current.content || '') + (data.response || ''),
                                thinking: data.thinking,
                                streaming: !data.final,
                            };
                            updated[idx] = next;
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
                const pIndex = updated.findIndex((m) => m.role === 'assistant' && (m.id === placeholderId || m.tempId === placeholderId || m.placeholder));
                const errorMsg = { id: placeholderId, role: 'assistant', content: `[Error: ${err.message}]`, placeholder: false, streaming: false };
                if (pIndex !== -1) {
                    updated[pIndex] = errorMsg;
                    return updated;
                }
                return [...prev, errorMsg];
            });
        } finally {
            setIsStreaming(false);
        }
    };

    return (
        <>
            <Header dark={dark} onToggleTheme={toggleTheme} onNewSession={newSession} />
            <div className={styles.mainLayout}>
                <div className={styles.column}>
                    <ChatInput onSend={sendMessage} disabled={isStreaming} />
                </div>
                <div className={styles.column}>
                    <ChatMessages messages={messages} />
                </div>
            </div>
        </>
    );
}

export default App;
