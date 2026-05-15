import { useState, useRef, useCallback } from 'react';

function _uuid() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
    return '10000000-1000-4000-8000-100000000000'.replace(/[018]/g, (c) =>
        (+c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (+c / 4)))).toString(16),
    );
}

/**
 * Build the request body for /api/chat.
 */
function _buildRequestBody(message, fileData, profileId, conversationId) {
    const body = { message: message || '(uploaded file)' };
    if (conversationId) body.conversation_id = conversationId;
    if (fileData) {
        body.data = [fileData];
    }
    if (profileId) body.profile_id = profileId;
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
    const payload = data.payload;
    if (!payload) return;

    const { type } = payload;
    const agentId = data.agent_id || null;

    // Content and turn_end are handled in the main loop, not here.
    if (type === 'content' || type === 'turn_end') return;

    // Agent started/finished → adds or updates a node in the agent tree
    if (type === 'agent_started' || type === 'agent_completed') {
        if (callbacks.onAgentEvent) callbacks.onAgentEvent(payload);
    }

    // Browser screenshot → shows in preview panel and as card thumbnail
    if (type === 'browser_screenshot') {
        callbacks.onBrowserSnapshot({
            url: payload.url,
            title: payload.title,
            screenshot: payload.screenshot,
            agentId,
        });
    }

    // Terminal output → shows in terminal panel
    if (type === 'terminal_output') {
        callbacks.onTerminalOutput({ ...payload, agentId });
    }

    // New custom tool was created → refresh the tools panel
    if (type === 'tool_created') {
        callbacks.onToolCreated();
    }

    // Tool call → update card badge, refresh memory if needed.
    // Activity log entry is buffered by the caller for correct ordering.
    if (type === 'tool_call') {
        if (payload.name === 'remember' || payload.name === 'forget') {
            callbacks.onMemoryChanged();
        }
        if (callbacks.onAgentToolCall) {
            callbacks.onAgentToolCall({ name: payload.name, agentId });
        }
    }

    if (type === 'audio_playback') {
        callbacks.onAudioPlayback({
            key: Date.now(),
            src: `data:${payload.content_type};base64,${payload.content}`,
        });
    }

    if (type === 'desktop_active') {
        callbacks.onDesktopActive(agentId);
    }

    if (type === 'generation_preview') {
        callbacks.onGenerationPreview({ ...payload, agentId });
    }

    if (type === 'file_output') {
        if (callbacks.onAgentFileOutput) {
            callbacks.onAgentFileOutput({ ...payload, agentId });
        }
    }

    // Context usage → agent card badges (iteration count, context fill)
    if (type === 'context_usage') {
        if (callbacks.onAgentContextUsage && agentId) {
            callbacks.onAgentContextUsage({
                agentId,
                iteration: payload.iteration || null,
                maxIterations: payload.max_iterations || null,
                contextUsage: {
                    context_used: payload.context_used,
                    context_limit: payload.context_limit,
                    fill_ratio: payload.fill_ratio,
                },
            });
        }
    }
}

/**
 * Convert raw LLM messages into UI-friendly message objects for display.
 *
 * Each assistant message becomes an `entries[]` carrying thinking, content,
 * and tool-call markers in chronological order — the same shape AgentOutput
 * renders during live streaming. Tool result messages are skipped: the chat
 * surface intentionally doesn't display them.
 */
function _historyToMessages(rawMessages) {
    const uiMessages = [];
    for (const msg of rawMessages) {
        if (msg.role === 'system' || msg.role === 'tool') continue;
        if (msg.role === 'user') {
            uiMessages.push({
                id: `hist_u_${uiMessages.length}`,
                role: 'user',
                content: msg.content || '',
            });
            continue;
        }
        if (msg.role === 'assistant') {
            const entries = [];
            if (msg.thinking) entries.push({ type: 'thinking', thinking: msg.thinking });
            if (msg.content) entries.push({ type: 'content', content: msg.content });
            for (const tc of (msg.tool_calls || [])) {
                entries.push({ type: 'tool_call', name: tc?.function?.name || '' });
            }
            if (entries.length === 0) continue;
            uiMessages.push({
                id: `hist_a_${uiMessages.length}`,
                role: 'assistant',
                entries,
                streaming: false,
            });
        }
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
    const rootAgentIdRef = useRef(null);

    const sendNudge = useCallback(async (message, agentId) => {
        if (!message) return;
        const nudgeBody = {
            message,
            conversation_id: conversationIdRef.current,
            agent_id: agentId || rootAgentIdRef.current,
        };
        try {
            const res = await fetch('/api/nudge', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(nudgeBody),
            });
            if (res.ok) {
                if (callbacks.onNudgeSent) callbacks.onNudgeSent({ ok: true, message });
            } else {
                const data = await res.json().catch(() => ({}));
                if (callbacks.onNudgeSent) callbacks.onNudgeSent({ ok: false, status: res.status, error: data.error });
            }
        } catch {
            if (callbacks.onNudgeSent) callbacks.onNudgeSent({ ok: false, status: 0, error: 'Could not reach the server' });
        }
    }, [callbacks]);

    const sendMessage = useCallback(async (message, fileData, profileId) => {
        if (!message && !fileData) return;

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

        const body = _buildRequestBody(message, fileData, profileId, conversationIdRef.current);

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

            // ── Activity log buffering ────────────────────────────────
            // Events arrive faster than React can render. We queue
            // everything in arrival order and flush once per animation
            // frame (~60fps). React 18 batches the dispatches into one
            // render, and the reducer merges consecutive same-type entries.
            const pending = [];

            const flush = () => {
                agentRafId = null;
                for (const op of pending) {
                    op.callback(op.args);
                }
                pending.length = 0;
            };

            const scheduleFlush = () => {
                if (agentRafId === null) {
                    agentRafId = requestAnimationFrame(flush);
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

                        const payload = data.payload;

                        _handleStreamEvent(data, callbacks);

                        // Set agentId on the assistant message so the chat
                        // view can look up this agent's activityLog.
                        if (payload?.type === 'agent_started' && !payload.parent_agent_id) {
                            rootAgentIdRef.current = payload.agent_id;
                            setMessages((prev) => {
                                const i = prev.length - 1;
                                if (i < 0 || prev[i].id !== assistantId) return prev;
                                const updated = [...prev];
                                updated[i] = { ...updated[i], agentId: payload.agent_id, streaming: true };
                                return updated;
                            });
                        }

                        if (payload?.type === 'content' && data.agent_id && callbacks.onAgentContent) {
                            const contentField = payload.content || '';
                            const hasResponse = contentField.length > 0;
                            const hasThinking = typeof payload.thinking === 'string' && payload.thinking.length > 0;
                            if (hasResponse || hasThinking) {
                                pending.push({
                                    callback: callbacks.onAgentContent,
                                    args: {
                                        agentId: data.agent_id,
                                        content: hasResponse ? contentField : null,
                                        thinking: hasThinking ? payload.thinking : null,
                                    },
                                });
                                scheduleFlush();
                            }
                        }

                        if (payload?.type === 'tool_call' && data.agent_id && callbacks.onActivityEntry) {
                            pending.push({
                                callback: callbacks.onActivityEntry,
                                args: {
                                    agentId: data.agent_id,
                                    entry: { type: 'tool_call', name: payload.name, timestamp: Date.now() },
                                },
                            });
                            scheduleFlush();
                        }

                        if (payload?.type === 'file_output' && data.agent_id && callbacks.onActivityEntry) {
                            pending.push({
                                callback: callbacks.onActivityEntry,
                                args: {
                                    agentId: data.agent_id,
                                    entry: { type: 'file_output', ...payload, timestamp: Date.now() },
                                },
                            });
                            scheduleFlush();
                        }

                        // Turn end — flush and mark done
                        if (payload?.type === 'turn_end') {
                            if (agentRafId !== null) {
                                cancelAnimationFrame(agentRafId);
                                agentRafId = null;
                            }
                            flush();
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
            // Stream ended — flush any remaining buffered entries
            flush();
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

    /** Clear messages and switch to a fresh conversation ID.
     *
     * Sends a best-effort stop for the previous conversation. The server
     * keeps an LRU cache of recent conversations and rehydrates from disk
     * on demand, so no explicit cache-eviction call is needed.
     */
    const newConversation = useCallback(() => {
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
            abortControllerRef.current = null;
        }
        const oldConversationId = conversationIdRef.current;
        fetch(`/api/chat/stop?conversation_id=${oldConversationId}`, { method: 'POST' }).catch(() => {});
        setIsStreaming(false);
        setMessages([]);
        conversationIdRef.current = _uuid();
    }, []);

    return {
        messages,
        isStreaming,
        sendMessage,
        sendNudge,
        stopGeneration,
        loadConversation,
        newConversation,
    };
}
