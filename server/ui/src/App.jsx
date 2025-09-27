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
            // Track segmentation of assistant output for this single user turn.
            // We gather all thinking until we receive a response; if more thinking comes AFTER a response,
            // we start a NEW assistant message (section) and repeat.
            let segmentIndex = 0;
            let currentAssistantId = placeholderId; // id for current segment message
            let currentHasResponse = false; // whether current segment has emitted any response text yet
            // Helper to ensure a segment message exists and optionally initialize
            const ensureAssistantMessage = (init = {}) => {
                setMessages((prev) => {
                    const updated = [...prev];
                    let idx = updated.findIndex(
                        (m) => m.role === 'assistant' && (m.id === currentAssistantId || m.tempId === currentAssistantId)
                    );
                    if (idx === -1) {
                        // Create a fresh assistant segment entry
                        updated.push({ id: currentAssistantId, role: 'assistant', content: '', thinking: undefined, placeholder: false, streaming: true, ...init });
                    } else {
                        // Make sure placeholder is cleared on first real data
                        updated[idx] = { ...updated[idx], placeholder: false, tempId: undefined, streaming: true, ...init };
                    }
                    return updated;
                });
            };
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
                        // Only support new 'content' field from event system
                        const contentField = typeof data.content === 'string' ? data.content : '';
                        const hasResponse = typeof contentField === 'string' && contentField.length > 0;
                        const hasThinking = typeof data.thinking === 'string' && data.thinking.length > 0;

                        // If thinking arrives AFTER we've already shown a response in this segment,
                        // start a new segment message to collect subsequent thinking.
                        if (hasThinking && currentHasResponse) {
                            segmentIndex += 1;
                            currentAssistantId = `${placeholderId}_s${segmentIndex}`;
                            currentHasResponse = false;
                            ensureAssistantMessage();
                        } else {
                            // Ensure the current segment message exists (clears placeholder)
                            ensureAssistantMessage();
                        }

                        // Now update the current segment with incoming data
                        setMessages((prev) => {
                            const updated = [...prev];
                            const i = updated.findIndex((m) => m.role === 'assistant' && m.id === currentAssistantId);
                            const cur = i === -1 ? { id: currentAssistantId, role: 'assistant', content: '', thinking: undefined } : updated[i];
                            const next = { ...cur };
                            if (hasThinking) {
                                const existing = typeof next.thinking === 'string' ? next.thinking : '';
                                // Use a visible separation (double newline) between distinct thinking chunks.
                                // Avoid adding extra newlines if existing already ends with blank line.
                                if (existing) {
                                    const endsWithBlank = /\n\s*$/.test(existing);
                                    next.thinking = endsWithBlank
                                        ? `${existing}${data.thinking}`
                                        : `${existing}\n\n${data.thinking}`;
                                } else {
                                    next.thinking = data.thinking;
                                }
                            }
                            if (hasResponse) {
                                const existingContent = next.content || '';
                                // If there is existing content and the new chunk does not start with a whitespace/newline
                                // and existing content does not already end with a newline, insert a newline separator.
                                // This addresses cases where the backend sends multiple discrete "response" chunks
                                // that should appear on separate lines (e.g., when two JSON objects / paragraphs arrive).
                                let toAppend = contentField;
                                if (existingContent) {
                                    const endsWithNewline = /\n\s*$/.test(existingContent);
                                    const startsWithBlock = /^\s*(?:```|\n)/.test(toAppend);
                                    if (!endsWithNewline && !startsWithBlock) {
                                        toAppend = '\n' + toAppend; // ensure visual separation
                                    }
                                }
                                next.content = existingContent + toAppend;
                                currentHasResponse = true;
                            }
                            // Only switch off streaming on final chunk; otherwise keep it on
                            if (data.final === true) {
                                next.streaming = false;
                            } else {
                                next.streaming = true;
                            }
                            updated[i === -1 ? updated.length : i] = next;
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
                    <div className={styles.stickyInput}>
                        <ChatInput onSend={sendMessage} disabled={isStreaming} />
                    </div>
                </div>
                <div className={styles.column}>
                    <ChatMessages messages={messages} />
                </div>
            </div>
        </>
    );
}

export default App;
