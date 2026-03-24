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
 * Handle non-text events that arrive on the stream (screenshots,
 * terminal output, agent lifecycle, tool calls, etc.).
 *
 * Each event type maps to a callback that DesktopApp provided.
 * Text tokens are handled separately in the main loop — this
 * function only deals with "something happened" events.
 */
function _handleStreamEvent(data, callbacks) {
    if (!data.event) return;

    const { type } = data.event;
    const agentId = data.agent_id || null;

    // Agent started/finished → adds or updates a node in the agent tree
    if (type === 'agent_started' || type === 'agent_completed') {
        if (callbacks.onAgentEvent) callbacks.onAgentEvent(data.event);
    }

    // Browser screenshot → shows in preview panel and as card thumbnail
    if (type === 'browser_screenshot') {
        callbacks.onBrowserSnapshot({
            url: data.event.url,
            title: data.event.title,
            screenshot: data.event.screenshot,
            agentId,
        });
    }

    // Terminal output → shows in terminal panel
    if (type === 'terminal_output') {
        callbacks.onTerminalOutput({ ...data.event, agentId });
    }

    // New custom tool was created → refresh the tools panel
    if (type === 'tool_created') {
        callbacks.onToolCreated();
    }

    // Tool call → show on agent card, log it, refresh memory if needed
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

    if (type === 'file_output') {
        if (callbacks.onAgentFileOutput) {
            callbacks.onAgentFileOutput({ ...data.event, agentId });
        }
    }

    // Context usage → agent card badges (iteration count, context fill)
    if (type === 'context_usage') {
        if (callbacks.onAgentContextUsage && agentId) {
            callbacks.onAgentContextUsage({
                agentId,
                iteration: data.event.iteration || null,
                maxIterations: data.event.max_iterations || null,
                contextUsage: {
                    context_used: data.event.context_used,
                    context_limit: data.event.context_limit,
                    fill_ratio: data.event.fill_ratio,
                },
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
                    entries: [{ type: 'content', content }],
                    streaming: false,
                });
            }
        }
        // Skip tool messages — they aren't displayed directly
    }
    return uiMessages;
}

/**
 * Manages the streaming chat connection with the backend.
 *
 * POSTs to /api/chat and reads the response as a stream of JSON lines.
 * Each line is either a text token or an event (screenshot, tool call, etc.).
 *
 * Root agent tokens are buffered and flushed into an ordered entries[]
 * array on the assistant message (~60fps via requestAnimationFrame).
 * Sub-agent tokens go to the agent reducer for the network/detail views.
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
            { id: placeholderId, role: 'assistant', placeholder: true },
        ]);

        const body = _buildRequestBody(message, fileData, modelSettings, conversationIdRef.current, agent);

        // IDs for pending animation frame flushes. Declared here so the
        // finally block can cancel them if the stream errors or aborts.
        let agentRafId = null;
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

            // ── Single message per turn ─────────────────────────────
            // One assistant message with an ordered entries[] array,
            // rendered identically to the agent activity view.
            const assistantId = placeholderId;

            // ── Token buffering ───────────────────────────────────────
            // Tokens arrive one word at a time. Updating React on every
            // single one would be way too slow. Instead we collect them
            // and flush once per screen paint (~60fps).
            //
            // ALL agent tokens (root and sub) go through the same path:
            //   bufferAgentToken → flushAgentBuffers → onAgentContent
            //   → agent reducer (APPEND_STREAM_CHUNK)
            //
            // The chat view reads the root agent's activityLog from the
            // reducer — same source as the activity view. No separate
            // buffer for root agent tokens.
            const agentPending = {};  // { [agentId]: { content: '', thinking: '' } }

            const flushAgentBuffers = () => {
                agentRafId = null;
                for (const [aid, buf] of Object.entries(agentPending)) {
                    if (!buf.content && !buf.thinking) continue;
                    if (callbacks.onAgentContent) {
                        callbacks.onAgentContent({
                            agentId: aid,
                            content: buf.content || null,
                            thinking: buf.thinking || null,
                        });
                    }
                    buf.content = '';
                    buf.thinking = '';
                }
            };

            const bufferAgentToken = (agentId, content, thinking) => {
                if (!agentPending[agentId]) agentPending[agentId] = { content: '', thinking: '' };
                if (content) agentPending[agentId].content += content;
                if (thinking) agentPending[agentId].thinking += thinking;
                if (agentRafId === null) {
                    agentRafId = requestAnimationFrame(flushAgentBuffers);
                }
            };

            // ── Process JSONL lines ────────────────────────────────
            // The backend streams one JSON object per line (JSONL).
            // reader.read() gives us arbitrary byte chunks, so we
            // accumulate into a buffer and extract complete lines
            // (up to each \n) one at a time.
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
                        const hasResponse = contentField.length > 0;
                        const hasThinking = typeof data.thinking === 'string' && data.thinking.length > 0;

                        // Set agentId on the assistant message so the chat
                        // view can look up this agent's activityLog.
                        if (data.event?.type === 'agent_started' && !data.event.parent_agent_id) {
                            setMessages((prev) => {
                                const i = prev.length - 1;
                                if (i < 0 || prev[i].id !== assistantId) return prev;
                                const updated = [...prev];
                                updated[i] = { ...updated[i], agentId: data.event.agent_id };
                                return updated;
                            });
                        }

                        // ── Text tokens ──────────────────────────────────
                        // All agents (root and sub) go through the same
                        // buffer → onAgentContent → agent reducer path.
                        if (data.agent_id && (hasResponse || hasThinking)) {
                            bufferAgentToken(
                                data.agent_id,
                                hasResponse ? contentField : null,
                                hasThinking ? data.thinking : null,
                            );
                        }

                        // Final marker — flush and mark done
                        if (data.final === true) {
                            flushAgentBuffers();
                            setMessages((prev) => {
                                const i = prev.length - 1;
                                if (i < 0 || prev[i].id !== assistantId) return prev;
                                const updated = [...prev];
                                updated[i] = { ...updated[i], streaming: false, placeholder: false };
                                return updated;
                            });
                        }
                    } catch (e) {
                        // ignore parse errors for partial/incomplete lines
                    }
                }
            }
            // Stream ended — flush any remaining buffered tokens
            flushAgentBuffers();
        } catch (err) {
            if (err.name === 'AbortError') return;
            // Replace the placeholder (or append) with an error message
            setMessages((prev) => {
                const updated = [...prev];
                const pIndex = updated.findIndex(
                    (m) => m.role === 'assistant' && (m.id === placeholderId || m.placeholder)
                );
                const errorMsg = {
                    id: placeholderId, role: 'assistant',
                    entries: [{ type: 'content', content: `[Error: ${err.message}]` }],
                    placeholder: false, streaming: false,
                };
                if (pIndex !== -1) {
                    updated[pIndex] = errorMsg;
                    return updated;
                }
                return [...prev, errorMsg];
            });
        } finally {
            if (agentRafId !== null) cancelAnimationFrame(agentRafId);
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
