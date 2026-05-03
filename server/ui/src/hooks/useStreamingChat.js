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

    // Tool call → show on agent card, log it, refresh memory if needed
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

    const sendMessage = useCallback(async (message, fileData, profileId) => {
        if (!message && !fileData) return;

        // If already streaming, send as a nudge (fire-and-forget)
        if (isStreamingRef.current) {
            const body = _buildRequestBody(message, fileData, profileId, conversationIdRef.current);
            fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
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
                headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
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

                        const payload = data.payload;

                        _handleStreamEvent(data, callbacks);

                        // Set agentId on the assistant message so the chat
                        // view can look up this agent's activityLog.
                        if (payload?.type === 'agent_started' && !payload.parent_agent_id) {
                            setMessages((prev) => {
                                const i = prev.length - 1;
                                if (i < 0 || prev[i].id !== assistantId) return prev;
                                const updated = [...prev];
                                updated[i] = { ...updated[i], agentId: payload.agent_id, streaming: true };
                                return updated;
                            });
                        }

                        // ── Text tokens ──────────────────────────────────
                        // All agents (root and sub) go through the same
                        // buffer → onAgentContent → agent reducer path.
                        if (payload?.type === 'content' && data.agent_id) {
                            const contentField = payload.content || '';
                            const hasResponse = contentField.length > 0;
                            const hasThinking = typeof payload.thinking === 'string' && payload.thinking.length > 0;
                            if (hasResponse || hasThinking) {
                                bufferAgentToken(
                                    data.agent_id,
                                    hasResponse ? contentField : null,
                                    hasThinking ? payload.thinking : null,
                                );
                            }
                        }

                        // Turn end — flush and mark done
                        if (payload?.type === 'turn_end') {
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
        fetch(`/api/chat/stop?conversation_id=${conversationIdRef.current}`, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } }).catch(() => {});
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
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
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
        fetch(`/api/chat/stop?conversation_id=${oldConversationId}`, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } }).catch(() => {});
        setIsStreaming(false);
        setMessages([]);
        conversationIdRef.current = _uuid();
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
