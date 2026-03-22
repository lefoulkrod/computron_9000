import { useState, useRef, useCallback } from 'react';

function _uuid() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
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
    const agentId = data.agent_id || null;

    if (type === 'agent_started' || type === 'agent_completed') {
        if (callbacks.onAgentEvent) callbacks.onAgentEvent(data.event);
    }

    if (type === 'browser_screenshot') {
        callbacks.onBrowserSnapshot({
            url: data.event.url,
            title: data.event.title,
            screenshot: data.event.screenshot,
            agentId,
        });
    }

    if (type === 'terminal_output') {
        callbacks.onTerminalOutput({ ...data.event, agentId });
    }

    if (type === 'tool_created') {
        callbacks.onToolCreated();
    }

    if (type === 'tool_call') {
        if (data.event.name === 'remember' || data.event.name === 'forget') {
            callbacks.onMemoryChanged();
        }
        if (callbacks.onAgentToolCall) {
            callbacks.onAgentToolCall({ name: data.event.name, agentId });
        }
    }

    if (type === 'audio_playback') {
        callbacks.onAudioPlayback({
            key: Date.now(),
            src: `data:${data.event.content_type};base64,${data.event.content}`,
        });
    }

    if (type === 'desktop_active') {
        callbacks.onDesktopActive(agentId);
    }

    if (type === 'generation_preview') {
        callbacks.onGenerationPreview({ ...data.event, agentId });
    }

    if (type === 'skill_applied') {
        if (callbacks.onSkillApplied) callbacks.onSkillApplied(data.event);
    }

    if (type === 'file_output') {
        if (callbacks.onAgentFileOutput) {
            callbacks.onAgentFileOutput({ ...data.event, agentId });
        }
    }

    // context_usage events are handled inline by the message component,
    // not as a side-effect callback. Pass iteration info to agent state.
    if (type === 'context_usage') {
        if (callbacks.onAgentContextUsage && agentId) {
            callbacks.onAgentContextUsage({
                agentId,
                iteration: data.event.iteration || null,
                maxIterations: data.event.max_iterations || null,
            });
        }
    }
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

/**
 * Hook that manages a streaming chat conversation with the backend.
 *
 * Connects to /api/chat via chunked JSONL streaming. Each JSONL line is either
 * a streaming token (data.delta=true) or a non-streaming event (tool calls,
 * context usage, screenshots, final marker, etc.).
 *
 * Streaming tokens are buffered and flushed once per animation frame to avoid
 * excessive React re-renders. Non-streaming events are applied immediately.
 *
 * Messages are segmented into separate bubbles when:
 *  - The agent depth changes (main agent ↔ sub-agent)
 *  - New thinking arrives after content (next tool-loop iteration)
 *
 * Returns: { messages, isStreaming, sendMessage, stopGeneration,
 *            loadConversation, newConversation }
 */
export default function useStreamingChat(callbacks) {
    const [messages, setMessages] = useState([]);
    const [isStreaming, _setIsStreaming] = useState(false);
    // Ref mirror of isStreaming so sendMessage can read it synchronously
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

        // Add user message + a placeholder "Thinking..." bubble
        const placeholderId = Math.random().toString(36).slice(2);
        setMessages((prev) => [
            ...prev,
            userMsg,
            { id: placeholderId, role: 'assistant', placeholder: true, tempId: placeholderId },
        ]);

        const body = _buildRequestBody(message, fileData, modelSettings, conversationIdRef.current, agent);

        let rafId = null;
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

            // ── Read the JSONL stream ────────────────────────────────
            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            // Segmentation state: a single user turn may produce multiple
            // assistant message bubbles (one per tool-loop iteration, plus
            // separate bubbles for sub-agents at different depths).
            let segmentIndex = 0;
            let currentAssistantId = placeholderId;
            let currentHasResponse = false;
            let currentDepth = 0;
            let currentAgentName = null;

            // Ensure the current segment's message object exists in state.
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

            // Buffer streaming tokens and flush once per animation frame
            // to avoid re-rendering on every single token.
            let pendingContent = '';
            let pendingThinking = '';

            const flushStreamBuffer = () => {
                rafId = null;
                if (!pendingContent && !pendingThinking) return;
                const contentChunk = pendingContent;
                const thinkingChunk = pendingThinking;
                pendingContent = '';
                pendingThinking = '';
                setMessages((prev) => {
                    const updated = [...prev];
                    const i = updated.findIndex(
                        (m) => m.role === 'assistant' && (m.id === currentAssistantId || m.tempId === currentAssistantId)
                    );
                    if (i === -1) return prev;
                    const next = { ...updated[i] };
                    // Clear placeholder so content renders during streaming
                    if (next.placeholder) {
                        next.placeholder = false;
                        next.tempId = undefined;
                        next.streaming = true;
                    }
                    if (currentAgentName) next.agent_name = currentAgentName;
                    if (currentDepth > 0) next.depth = currentDepth;
                    if (contentChunk) {
                        next.content = (next.content || '') + contentChunk;
                    }
                    if (thinkingChunk) {
                        next.thinking = (next.thinking || '') + thinkingChunk;
                    }
                    updated[i] = next;
                    return updated;
                });
            };

            const scheduleStreamFlush = () => {
                if (rafId === null) {
                    rafId = requestAnimationFrame(flushStreamBuffer);
                }
            };

            // Mark a segment as done streaming
            const finishSegment = (oldId) => {
                setMessages((prev) => {
                    const idx = prev.findIndex((m) => m.id === oldId);
                    if (idx === -1 || !prev[idx].streaming) return prev;
                    const updated = [...prev];
                    updated[idx] = { ...updated[idx], streaming: false };
                    return updated;
                });
            };

            // ── Process JSONL lines ────────────────────────────────
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

                        _handleStreamEvent(data, callbacks);

                        // Extract fields from the JSONL event
                        const contentField = typeof data.content === 'string' ? data.content : '';
                        const hasResponse = typeof contentField === 'string' && contentField.length > 0;
                        const hasThinking = typeof data.thinking === 'string' && data.thinking.length > 0;
                        const agentName = data.agent_name || null;
                        const depth = typeof data.depth === 'number' ? data.depth : 0;
                        const dataField = Array.isArray(data.data) && data.data.length > 0 ? data.data : null;
                        const toolCallEvent = data.event && data.event.type === 'tool_call' ? data.event : null;
                        const fileOutputEvent = data.event && data.event.type === 'file_output' ? data.event : null;
                        const contextUsageEvent = data.event && data.event.type === 'context_usage' ? data.event : null;

                        // Finish the current segment and start a new one when
                        // depth changes (main ↔ sub-agent) or when new thinking
                        // arrives after content (next tool-loop iteration).
                        const maybeNewSegment = (evtDepth, hasThink) => {
                            const depthChanged = (evtDepth > 0 && currentDepth === 0)
                                || (evtDepth === 0 && currentDepth > 0);
                            if (!depthChanged && !(hasThink && currentHasResponse)) return;

                            flushStreamBuffer();
                            if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null; }
                            finishSegment(currentAssistantId);
                            segmentIndex += 1;
                            if (evtDepth > 0 && currentDepth === 0) {
                                currentAssistantId = `${placeholderId}_sub_${segmentIndex}`;
                            } else if (evtDepth === 0 && currentDepth > 0) {
                                currentAssistantId = `${placeholderId}_main_${segmentIndex}`;
                            } else {
                                currentAssistantId = `${placeholderId}_s${segmentIndex}`;
                            }
                            currentHasResponse = false;
                            currentDepth = evtDepth;
                            ensureAssistantMessage();
                        };

                        // ── Streaming tokens ──────────────────────────────
                        // Buffer content/thinking and flush once per frame.
                        // Sub-agent tokens (depth > 0) route to agent state,
                        // not to chat messages.
                        if (data.delta && !dataField && !toolCallEvent && !fileOutputEvent
                            && !contextUsageEvent && data.final !== true) {
                            if (depth > 0 && data.agent_id) {
                                // Route sub-agent tokens to agent state
                                if (callbacks.onAgentContent && (hasResponse || hasThinking)) {
                                    callbacks.onAgentContent({
                                        agentId: data.agent_id,
                                        content: hasResponse ? contentField : null,
                                        thinking: hasThinking ? data.thinking : null,
                                    });
                                }
                                continue;
                            }
                            if (agentName) currentAgentName = agentName;
                            maybeNewSegment(depth, hasThinking);
                            if (hasResponse) {
                                pendingContent += contentField;
                                currentHasResponse = true;
                            }
                            if (hasThinking) pendingThinking += data.thinking;
                            if (hasResponse || hasThinking) scheduleStreamFlush();
                            continue;
                        }

                        // ── Non-streaming events ──────────────────────────
                        // Tool calls, context usage, screenshots, final marker.
                        // Sub-agent non-streaming content also routes to agent state.
                        if (depth > 0 && data.agent_id && !data.final) {
                            if ((hasResponse || hasThinking) && callbacks.onAgentContent) {
                                callbacks.onAgentContent({
                                    agentId: data.agent_id,
                                    content: hasResponse ? contentField : null,
                                    thinking: hasThinking ? data.thinking : null,
                                });
                            }
                            continue;
                        }

                        // Flush buffered tokens first so ordering is preserved.
                        flushStreamBuffer();
                        if (rafId !== null) {
                            cancelAnimationFrame(rafId);
                            rafId = null;
                        }
                        maybeNewSegment(depth, hasThinking);
                        ensureAssistantMessage();

                        // Apply event data, metadata, and complete-chunk
                        // content/thinking to the current segment.
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
            // Stream ended — flush any remaining buffered tokens
            flushStreamBuffer();
        } catch (err) {
            if (rafId !== null) cancelAnimationFrame(rafId);
            if (err.name === 'AbortError') return;
            // Replace the placeholder (or append) with an error message
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

    /** Ask the backend to stop generation and update local state. */
    const stopGeneration = useCallback(() => {
        fetch(`/api/chat/stop?conversation_id=${conversationIdRef.current}`, { method: 'POST' }).catch(() => {});
        setIsStreaming(false);
    }, []);

    /** Resume a previous conversation by loading its history from the backend. */
    const loadConversation = useCallback(async (conversationId) => {
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

    /** Clear messages, generate a fresh conversation ID, and delete backend history. */
    const newConversation = useCallback(async () => {
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
        loadConversation,
        newConversation,
    };
}
