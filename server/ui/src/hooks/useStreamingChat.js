import { useState, useRef, useCallback } from 'react';

function _uuid() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) return _uuid();
    return '10000000-1000-4000-8000-100000000000'.replace(/[018]/g, (c) =>
        (+c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (+c / 4)))).toString(16),
    );
}

/**
 * Build the request body for /api/chat including model options.
 */
function _buildRequestBody(message, fileData, modelSettings, conversationId, agent) {
    const body = { message: message || '(uploaded file)' };
    if (conversationId) body.conversation_id = conversationId;
    if (agent) body.agent = agent;
    if (fileData) {
        body.data = [fileData];
    }
    const opts = {};
    const { selectedModel, contextKb, think, persistThinking, temperature, topK, topP, repeatPenalty,
        numPredict, unlimitedTurns, agentTurns } = modelSettings;
    if (selectedModel) opts.model = selectedModel;
    if (contextKb !== '') opts.num_ctx = parseInt(contextKb, 10) * 1000;
    opts.think = think;
    if (persistThinking !== undefined) opts.persist_thinking = persistThinking;
    if (temperature !== '') opts.temperature = parseFloat(temperature);
    if (topK !== '') opts.top_k = parseInt(topK, 10);
    if (topP !== '') opts.top_p = parseFloat(topP);
    if (repeatPenalty !== '') opts.repeat_penalty = parseFloat(repeatPenalty);
    if (numPredict !== '' && numPredict !== undefined) opts.num_predict = parseInt(numPredict, 10);
    if (!unlimitedTurns && agentTurns !== '') opts.max_iterations = parseInt(agentTurns, 10);
    if (Object.keys(opts).length > 0) body.options = opts;
    return body;
}

/**
 * Dispatch side-effect events (browser screenshot, terminal output, etc.)
 * to the callbacks provided by the consuming component.
 */
function _handleStreamEvent(data, callbacks) {
    if (!data.event) return;

    const { type } = data.event;

    if (type === 'browser_screenshot') {
        callbacks.onBrowserSnapshot({
            url: data.event.url,
            title: data.event.title,
            screenshot: data.event.screenshot,
        });
    }

    if (type === 'terminal_output') {
        callbacks.onTerminalOutput(data.event);
    }

    if (type === 'tool_created') {
        callbacks.onToolCreated();
    }

    if (type === 'tool_call' &&
        (data.event.name === 'remember' || data.event.name === 'forget')) {
        callbacks.onMemoryChanged();
    }

    if (type === 'audio_playback') {
        callbacks.onAudioPlayback({
            key: Date.now(),
            src: `data:${data.event.content_type};base64,${data.event.content}`,
        });
    }

    if (type === 'desktop_active') {
        callbacks.onDesktopActive();
    }

    if (type === 'generation_preview') {
        callbacks.onGenerationPreview(data.event);
    }

    if (type === 'skill_applied') {
        callbacks.onSkillApplied(data.event);
    }

    // context_usage events are handled inline by the message component,
    // not as a side-effect callback.
}

/**
 * Convert raw LLM messages into UI-friendly message objects for display.
 */
function _historyToMessages(rawMessages) {
    const uiMessages = [];
    for (const msg of rawMessages) {
        if (msg.role === 'system') continue;
        if (msg.role === 'user') {
            uiMessages.push({
                id: `hist_u_${uiMessages.length}`,
                role: 'user',
                content: msg.content || '',
            });
        } else if (msg.role === 'assistant') {
            const content = msg.content || '';
            if (content) {
                uiMessages.push({
                    id: `hist_a_${uiMessages.length}`,
                    role: 'assistant',
                    content,
                    streaming: false,
                    agent_name: msg.agent_name || null,
                });
            }
        }
        // Skip tool messages — they aren't displayed directly
    }
    return uiMessages;
}

export default function useStreamingChat(callbacks) {
    const [messages, setMessages] = useState([]);
    const [isStreaming, _setIsStreaming] = useState(false);
    const isStreamingRef = useRef(false);
    const setIsStreaming = useCallback((val) => {
        isStreamingRef.current = val;
        _setIsStreaming(val);
    }, []);
    const abortControllerRef = useRef(null);
    const conversationIdRef = useRef(_uuid());

    const sendMessage = useCallback(async (message, fileData, modelSettings, agent) => {
        if (!message && !fileData) return;

        // If already streaming, send as a nudge (fire-and-forget)
        if (isStreamingRef.current) {
            const body = _buildRequestBody(message, fileData, modelSettings, conversationIdRef.current, agent);
            fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            }).catch(() => {});
            if (callbacks.onNudgeSent) callbacks.onNudgeSent(message || '');
            return;
        }

        // Build user message with optional attachment preview
        const userMsg = {
            id: `u_${Date.now()}_${Math.random().toString(36).slice(2)}`,
            role: 'user',
            content: message || '',
        };
        if (fileData && fileData.content_type && fileData.content_type.startsWith('image/')) {
            userMsg.images = [`data:${fileData.content_type};base64,${fileData.base64}`];
        } else if (fileData && fileData.filename) {
            userMsg.files = [{ filename: fileData.filename, content_type: fileData.content_type }];
        }

        const placeholderId = Math.random().toString(36).slice(2);
        setMessages((prev) => [
            ...prev,
            userMsg,
            { id: placeholderId, role: 'assistant', placeholder: true, tempId: placeholderId },
        ]);

        const body = _buildRequestBody(message, fileData, modelSettings, conversationIdRef.current, agent);

        try {
            const controller = new AbortController();
            abortControllerRef.current = controller;
            setIsStreaming(true);

            const resp = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
                signal: controller.signal,
            });
            if (!resp.body) return;

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            // Track segmentation of assistant output for this single user turn.
            let segmentIndex = 0;
            let currentAssistantId = placeholderId;
            let currentHasResponse = false;
            // Depth tracking: sub-agents (depth > 0) get their own message bubbles
            let currentDepth = 0;

            // Helper to ensure a segment message exists and optionally initialize
            const ensureAssistantMessage = (init = {}) => {
                setMessages((prev) => {
                    const updated = [...prev];
                    let idx = updated.findIndex(
                        (m) => m.role === 'assistant' && (m.id === currentAssistantId || m.tempId === currentAssistantId)
                    );
                    if (idx === -1) {
                        updated.push({
                            id: currentAssistantId, role: 'assistant',
                            content: '', thinking: undefined,
                            placeholder: false, streaming: true, ...init,
                        });
                    } else {
                        updated[idx] = {
                            ...updated[idx], placeholder: false,
                            tempId: undefined, streaming: true, ...init,
                        };
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

                        // Dispatch side-effect events
                        _handleStreamEvent(data, callbacks);

                        const contentField = typeof data.content === 'string' ? data.content : '';
                        const hasResponse = typeof contentField === 'string' && contentField.length > 0;
                        const hasThinking = typeof data.thinking === 'string' && data.thinking.length > 0;
                        const agentName = data.agent_name || null;
                        const depth = typeof data.depth === 'number' ? data.depth : 0;
                        const dataField = Array.isArray(data.data) ? data.data : null;
                        const toolCallEvent = data.event && data.event.type === 'tool_call' ? data.event : null;
                        const fileOutputEvent = data.event && data.event.type === 'file_output' ? data.event : null;
                        const contextUsageEvent = data.event && data.event.type === 'context_usage' ? data.event : null;

                        // Handle depth transitions: sub-agents get their own message bubbles
                        if (depth > 0 && currentDepth === 0) {
                            segmentIndex += 1;
                            currentAssistantId = `${placeholderId}_sub_${segmentIndex}`;
                            currentHasResponse = false;
                            currentDepth = depth;
                        } else if (depth === 0 && currentDepth > 0) {
                            segmentIndex += 1;
                            currentAssistantId = `${placeholderId}_main_${segmentIndex}`;
                            currentHasResponse = false;
                            currentDepth = 0;
                        }

                        // If thinking arrives after a response in this segment, start a new segment
                        if (hasThinking && currentHasResponse) {
                            segmentIndex += 1;
                            currentAssistantId = `${placeholderId}_s${segmentIndex}`;
                            currentHasResponse = false;
                            ensureAssistantMessage();
                        } else {
                            ensureAssistantMessage();
                        }

                        // Update the current segment with incoming data
                        setMessages((prev) => {
                            const updated = [...prev];
                            const i = updated.findIndex((m) => m.role === 'assistant' && m.id === currentAssistantId);
                            const cur = i === -1
                                ? { id: currentAssistantId, role: 'assistant', content: '', thinking: undefined }
                                : updated[i];
                            const next = { ...cur };

                            if (agentName) next.agent_name = agentName;
                            if (typeof depth === 'number') next.depth = depth;

                            if (dataField) {
                                const existing = Array.isArray(next.data) ? next.data : [];
                                next.data = [...existing, ...dataField];
                            }
                            if (toolCallEvent) {
                                const existing = Array.isArray(next.data) ? next.data : [];
                                next.data = [...existing, toolCallEvent];
                            }
                            if (fileOutputEvent) {
                                const existing = Array.isArray(next.data) ? next.data : [];
                                next.data = [...existing, fileOutputEvent];
                            }

                            if (contextUsageEvent) {
                                next.contextUsage = contextUsageEvent;
                            }

                            if (hasThinking) {
                                const existing = typeof next.thinking === 'string' ? next.thinking : '';
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
                                let toAppend = contentField;
                                if (existingContent) {
                                    const endsWithNewline = /\n\s*$/.test(existingContent);
                                    const startsWithBlock = /^\s*(?:```|\n)/.test(toAppend);
                                    if (!endsWithNewline && !startsWithBlock) {
                                        toAppend = '\n' + toAppend;
                                    }
                                }
                                next.content = existingContent + toAppend;
                                currentHasResponse = true;
                            }

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
            if (err.name === 'AbortError') return;
            setMessages((prev) => {
                const updated = [...prev];
                const pIndex = updated.findIndex(
                    (m) => m.role === 'assistant' && (m.id === placeholderId || m.tempId === placeholderId || m.placeholder)
                );
                const errorMsg = {
                    id: placeholderId, role: 'assistant',
                    content: `[Error: ${err.message}]`,
                    placeholder: false, streaming: false,
                };
                if (pIndex !== -1) {
                    updated[pIndex] = errorMsg;
                    return updated;
                }
                return [...prev, errorMsg];
            });
        } finally {
            abortControllerRef.current = null;
            setIsStreaming(false);
        }
    }, [callbacks]);

    const stopGeneration = useCallback(() => {
        fetch(`/api/chat/stop?conversation_id=${conversationIdRef.current}`, { method: 'POST' }).catch(() => {});
        setIsStreaming(false);
    }, []);

    const loadSession = useCallback(async (conversationId) => {
        // Abort any in-flight stream
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
            abortControllerRef.current = null;
        }
        setIsStreaming(false);

        try {
            const resp = await fetch(`/api/conversations/sessions/${conversationId}/resume`, {
                method: 'POST',
            });
            if (!resp.ok) return false;
            const data = await resp.json();
            conversationIdRef.current = conversationId;
            setMessages(_historyToMessages(data.messages || []));
            return true;
        } catch (_) {
            return false;
        }
    }, []);

    const newSession = useCallback(async () => {
        // Abort any in-flight stream so it doesn't write into the cleared message list
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
            abortControllerRef.current = null;
        }
        const oldConversationId = conversationIdRef.current;
        fetch(`/api/chat/stop?conversation_id=${oldConversationId}`, { method: 'POST' }).catch(() => {});
        setIsStreaming(false);
        setMessages([]);
        // Generate a fresh conversation ID for the new conversation
        conversationIdRef.current = _uuid();
        try {
            await fetch(`/api/chat/history?conversation_id=${oldConversationId}`, { method: 'DELETE' });
        } catch (err) {
            // ignore
        }
    }, []);

    return {
        messages,
        isStreaming,
        sendMessage,
        stopGeneration,
        loadSession,
        newSession,
    };
}
