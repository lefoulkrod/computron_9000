# Human-in-the-Loop (HITL) Design for Computron 9000

## Executive Summary

This document outlines a comprehensive Human-in-the-Loop (HITL) system design that integrates seamlessly with Computron 9000's existing event-driven architecture and turn-based execution model. The design enables agents to pause execution at critical decision points, request human input, and resume with human-provided guidance.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EXISTING ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  HTTP API (aiohttp_app.py)                                                  │
│       │                                                                     │
│       ▼                                                                     │
│  Message Handler (message_handler.py)                                       │
│       │                                                                     │
│       ▼                                                                     │
│  Turn Scope (sdk/turn/_turn.py) ──► Event Dispatcher (sdk/events/)          │
│       │                              │                                      │
│       ▼                              ▼                                      │
│  Tool Loop (sdk/turn/_execution.py)  AgentEvent Stream ──► Frontend        │
│       │                                                                     │
│       ▼                                                                     │
│  Hooks (sdk/hooks/)                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ▲
                                      │
┌─────────────────────────────────────────────────────────────────────────────┐
│                         NEW HITL COMPONENTS                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│  │  HITL Hook      │───►│  Checkpoint     │───►│  Resume Queue   │         │
│  │  (sdk/hooks/)   │    │  Manager        │    │  (asyncio)      │         │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘         │
│          │                       │                      │                   │
│          ▼                       ▼                      ▼                   │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│  │  HITL Events    │    │  State Store    │    │  API Endpoints  │         │
│  │  (sdk/events/)   │    │  (Redis/Mem)    │    │  (server/)      │         │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Core HITL Infrastructure

### 1.1 New Event Types (sdk/events/_models.py)

Add new payload types to the existing `AgentEventPayload` union:

```python
class HumanInputRequestPayload(BaseModel):
    """Emitted when an agent requires human input before proceeding.
    
    Attributes:
        type: Discriminator; always "human_input_request".
        checkpoint_id: Unique identifier for this checkpoint.
        agent_id: The agent requesting input.
        context: Human-readable description of what input is needed.
        options: Optional predefined choices for the user.
        timeout_seconds: How long to wait before auto-resuming (0 = indefinite).
        blocking_tools: List of tool names that will be blocked until resolved.
    """
    type: Literal["human_input_request"]
    checkpoint_id: str
    agent_id: str
    context: str
    options: list[dict[str, str]] | None = None  # [{"id": "approve", "label": "Approve"}]
    timeout_seconds: int = 0
    blocking_tools: list[str] | None = None


class HumanInputReceivedPayload(BaseModel):
    """Emitted when human input has been received and processed.
    
    Attributes:
        type: Discriminator; always "human_input_received".
        checkpoint_id: Matches the request that was fulfilled.
        response_type: How the human responded (text/choice/abort).
        response_value: The actual response content.
        responder_id: Identifier of the human who responded.
        response_time_ms: Time taken to respond.
    """
    type: Literal["human_input_received"]
    checkpoint_id: str
    response_type: Literal["text", "choice", "abort", "timeout"]
    response_value: str | None = None
    responder_id: str | None = None
    response_time_ms: int | None = None


class CheckpointStatePayload(BaseModel):
    """Emitted to show current checkpoint status.
    
    Attributes:
        type: Discriminator; always "checkpoint_state".
        checkpoint_id: The checkpoint being reported on.
        state: Current state (pending, acknowledged, fulfilled, expired).
        created_at: When the checkpoint was created.
        acknowledged_at: When first viewed by a human.
        fulfilled_at: When response was provided.
    """
    type: Literal["checkpoint_state"]
    checkpoint_id: str
    state: Literal["pending", "acknowledged", "fulfilled", "expired", "aborted"]
    created_at: datetime
    acknowledged_at: datetime | None = None
    fulfilled_at: datetime | None = None
```

**Integration Point**: Add these to `AgentEventPayload` union in `_models.py`:
```python
AgentEventPayload = Annotated[
    ContentPayload
    | TurnEndPayload
    | ...
    | HumanInputRequestPayload      # NEW
    | HumanInputReceivedPayload     # NEW
    | CheckpointStatePayload,       # NEW
    Field(discriminator="type"),
]
```

---

### 1.2 Checkpoint Manager (sdk/hitl/_checkpoint.py)

```python
"""Checkpoint management for human-in-the-loop interactions.

Checkpoints represent points in execution where the agent requires
human input before proceeding. The CheckpointManager handles:
- Creating and tracking checkpoints
- Waiting for human responses (async)
- Timeout handling
- State persistence
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sdk.events._models import HumanInputRequestPayload

logger = logging.getLogger(__name__)


class CheckpointState(Enum):
    PENDING = auto()
    ACKNOWLEDGED = auto()  # Human has seen the request
    FULFILLED = auto()     # Human has provided input
    EXPIRED = auto()       # Timeout reached
    ABORTED = auto()       # Turn was stopped


@dataclass
class Checkpoint:
    """Represents a single human input checkpoint."""
    checkpoint_id: str
    agent_id: str
    context: str
    options: list[dict[str, str]] | None
    timeout_seconds: int
    blocking_tools: list[str] | None
    state: CheckpointState = field(default=CheckpointState.PENDING)
    created_at: datetime = field(default_factory=datetime.utcnow)
    acknowledged_at: datetime | None = None
    fulfilled_at: datetime | None = None
    response_value: str | None = None
    response_type: str | None = None
    responder_id: str | None = None
    
    # Async primitives for waiting
    _fulfilled_event: asyncio.Event = field(default_factory=asyncio.Event)
    _response_future: asyncio.Future[str | None] = field(default_factory=asyncio.Future)


class CheckpointManager:
    """Manages checkpoints for a single conversation.
    
    This class is designed to be instantiated per-turn and tracks
    all checkpoints created during that turn.
    """
    
    def __init__(self, conversation_id: str) -> None:
        self._conversation_id = conversation_id
        self._checkpoints: dict[str, Checkpoint] = {}
        self._lock = asyncio.Lock()
        
    async def create_checkpoint(
        self,
        agent_id: str,
        context: str,
        options: list[dict[str, str]] | None = None,
        timeout_seconds: int = 0,
        blocking_tools: list[str] | None = None,
    ) -> Checkpoint:
        """Create a new checkpoint and return it.
        
        The checkpoint starts in PENDING state. Callers should emit
        a HumanInputRequestPayload event after creation.
        """
        checkpoint_id = f"{self._conversation_id}.{uuid.uuid4().hex[:8]}"
        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            agent_id=agent_id,
            context=context,
            options=options,
            timeout_seconds=timeout_seconds,
            blocking_tools=blocking_tools,
        )
        
        async with self._lock:
            self._checkpoints[checkpoint_id] = checkpoint
            
        logger.info(
            "Created checkpoint %s for agent %s (timeout=%s)",
            checkpoint_id, agent_id, timeout_seconds,
        )
        return checkpoint
    
    async def acknowledge_checkpoint(self, checkpoint_id: str) -> bool:
        """Mark a checkpoint as acknowledged (human has seen it)."""
        async with self._lock:
            checkpoint = self._checkpoints.get(checkpoint_id)
            if not checkpoint:
                return False
            if checkpoint.state == CheckpointState.PENDING:
                checkpoint.state = CheckpointState.ACKNOWLEDGED
                checkpoint.acknowledged_at = datetime.utcnow()
                logger.debug("Checkpoint %s acknowledged", checkpoint_id)
        return True
    
    async def fulfill_checkpoint(
        self,
        checkpoint_id: str,
        response_type: str,
        response_value: str | None,
        responder_id: str | None = None,
    ) -> bool:
        """Fulfill a checkpoint with human input."""
        async with self._lock:
            checkpoint = self._checkpoints.get(checkpoint_id)
            if not checkpoint:
                return False
            if checkpoint.state in (CheckpointState.FULFILLED, CheckpointState.EXPIRED, CheckpointState.ABORTED):
                return False
                
            checkpoint.state = CheckpointState.FULFILLED
            checkpoint.fulfilled_at = datetime.utcnow()
            checkpoint.response_type = response_type
            checkpoint.response_value = response_value
            checkpoint.responder_id = responder_id
            
            # Signal waiting coroutines
            checkpoint._fulfilled_event.set()
            if not checkpoint._response_future.done():
                checkpoint._response_future.set_result(response_value)
                
        logger.info(
            "Checkpoint %s fulfilled by %s (type=%s)",
            checkpoint_id, responder_id, response_type,
        )
        return True
    
    async def wait_for_response(
        self,
        checkpoint_id: str,
    ) -> tuple[str | None, str]:
        """Wait for a checkpoint to be fulfilled.
        
        Returns:
            Tuple of (response_value, response_type).
            For abort/timeout, response_value may be None.
        """
        checkpoint = self._checkpoints.get(checkpoint_id)
        if not checkpoint:
            raise ValueError(f"Checkpoint {checkpoint_id} not found")
            
        # Check if already fulfilled
        if checkpoint.state == CheckpointState.FULFILLED:
            return checkpoint.response_value, checkpoint.response_type or "unknown"
            
        # Set up timeout if specified
        if checkpoint.timeout_seconds > 0:
            try:
                await asyncio.wait_for(
                    checkpoint._fulfilled_event.wait(),
                    timeout=checkpoint.timeout_seconds,
                )
            except asyncio.TimeoutError:
                async with self._lock:
                    checkpoint.state = CheckpointState.EXPIRED
                    checkpoint.response_type = "timeout"
                    checkpoint._fulfilled_event.set()
                    if not checkpoint._response_future.done():
                        checkpoint._response_future.set_result(None)
                logger.warning("Checkpoint %s timed out", checkpoint_id)
                return None, "timeout"
        else:
            # Wait indefinitely
            await checkpoint._fulfilled_event.wait()
            
        return checkpoint.response_value, checkpoint.response_type or "unknown"
    
    async def abort_all(self) -> None:
        """Abort all pending checkpoints (e.g., when turn is stopped)."""
        async with self._lock:
            for checkpoint in self._checkpoints.values():
                if checkpoint.state in (CheckpointState.PENDING, CheckpointState.ACKNOWLEDGED):
                    checkpoint.state = CheckpointState.ABORTED
                    checkpoint.response_type = "abort"
                    checkpoint._fulfilled_event.set()
                    if not checkpoint._response_future.done():
                        checkpoint._response_future.set_result(None)
        logger.info("Aborted all checkpoints for conversation %s", self._conversation_id)
    
    def get_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        """Get a checkpoint by ID."""
        return self._checkpoints.get(checkpoint_id)
    
    def list_checkpoints(
        self,
        agent_id: str | None = None,
        state: CheckpointState | None = None,
    ) -> list[Checkpoint]:
        """List checkpoints with optional filtering."""
        result = list(self._checkpoints.values())
        if agent_id:
            result = [c for c in result if c.agent_id == agent_id]
        if state:
            result = [c for c in result if c.state == state]
        return result


# Global registry of checkpoint managers per conversation
_checkpoint_managers: dict[str, CheckpointManager] = {}


def get_checkpoint_manager(conversation_id: str) -> CheckpointManager:
    """Get or create the checkpoint manager for a conversation."""
    if conversation_id not in _checkpoint_managers:
        _checkpoint_managers[conversation_id] = CheckpointManager(conversation_id)
    return _checkpoint_managers[conversation_id]


def remove_checkpoint_manager(conversation_id: str) -> None:
    """Remove the checkpoint manager for a conversation (cleanup)."""
    _checkpoint_managers.pop(conversation_id, None)
```

---

### 1.3 HITL Hook (sdk/hitl/_hook.py)

```python
"""HITL Hook — integrates human-in-the-loop checkpoints into the tool loop.

This hook intercepts tool calls at the before_tool phase, checks if the
tool is in a blocking list, and if so, creates a checkpoint and waits
for human approval before allowing execution.
"""

from __future__ import annotations

import logging
from typing import Any

from sdk.events import (
    AgentEvent,
    CheckpointStatePayload,
    HumanInputReceivedPayload,
    HumanInputRequestPayload,
    publish_event,
)
from sdk.events._context import get_current_agent_id, get_current_agent_name

from ._checkpoint import CheckpointManager, CheckpointState, get_checkpoint_manager

logger = logging.getLogger(__name__)


class HITLHook:
    """Hook that enables human-in-the-loop approval for tool calls.
    
    Configuration options:
    - require_approval_for: List of tool names requiring approval
    - require_approval_patterns: Regex patterns matching tool names
    - default_timeout: Default timeout for human responses
    - auto_approve_on_timeout: Whether to auto-approve or reject on timeout
    """
    
    def __init__(
        self,
        conversation_id: str,
        require_approval_for: list[str] | None = None,
        require_approval_patterns: list[str] | None = None,
        default_timeout: int = 0,
        auto_approve_on_timeout: bool = False,
    ) -> None:
        self._conversation_id = conversation_id
        self._require_approval = set(require_approval_for or [])
        self._approval_patterns = require_approval_patterns or []
        self._default_timeout = default_timeout
        self._auto_approve_on_timeout = auto_approve_on_timeout
        self._checkpoint_manager = get_checkpoint_manager(conversation_id)
        self._pending_tool_calls: dict[str, Any] = {}  # checkpoint_id -> tool_call
        
    def _tool_requires_approval(self, tool_name: str) -> bool:
        """Check if a tool requires human approval."""
        if tool_name in self._require_approval:
            return True
        import re
        for pattern in self._approval_patterns:
            if re.match(pattern, tool_name):
                return True
        return False
    
    def before_tool(self, tool_name: str, tool_arguments: dict[str, Any]) -> str | None:
        """Intercept tool calls that require human approval.
        
        Returns:
            None to allow normal execution, or a string result to skip
            execution and use the provided result instead.
        """
        if not self._tool_requires_approval(tool_name):
            return None
            
        # This is a sync method but we need async - we'll use a different approach
        # The actual implementation will be in the async version
        return None
    
    async def before_tool_async(
        self,
        tool_name: str,
        tool_arguments: dict[str, Any],
    ) -> str | None:
        """Async version of before_tool for checkpoint-based approval.
        
        This is called by the HITL-aware tool wrapper.
        """
        if not self._tool_requires_approval(tool_name):
            return None
            
        agent_id = get_current_agent_id() or "unknown"
        agent_name = get_current_agent_name() or "Unknown Agent"
        
        # Create checkpoint
        context = self._build_context(tool_name, tool_arguments, agent_name)
        checkpoint = await self._checkpoint_manager.create_checkpoint(
            agent_id=agent_id,
            context=context,
            options=[
                {"id": "approve", "label": "Approve", "style": "primary"},
                {"id": "reject", "label": "Reject", "style": "danger"},
                {"id": "modify", "label": "Modify & Approve", "style": "secondary"},
            ],
            timeout_seconds=self._default_timeout,
            blocking_tools=[tool_name],
        )
        
        # Emit request event
        publish_event(AgentEvent(payload=HumanInputRequestPayload(
            type="human_input_request",
            checkpoint_id=checkpoint.checkpoint_id,
            agent_id=agent_id,
            context=context,
            options=checkpoint.options,
            timeout_seconds=checkpoint.timeout_seconds,
            blocking_tools=checkpoint.blocking_tools,
        )))
        
        # Wait for response
        response_value, response_type = await self._checkpoint_manager.wait_for_response(
            checkpoint.checkpoint_id
        )
        
        # Emit received event
        publish_event(AgentEvent(payload=HumanInputReceivedPayload(
            type="human_input_received",
            checkpoint_id=checkpoint.checkpoint_id,
            response_type=response_type,
            response_value=response_value,
        )))
        
        # Handle response
        if response_type == "abort":
            from sdk.turn._turn import StopRequestedError
            raise StopRequestedError()
            
        if response_type == "timeout":
            if self._auto_approve_on_timeout:
                logger.warning("Checkpoint %s timed out, auto-approving", checkpoint.checkpoint_id)
                return None  # Allow execution
            else:
                return f"Tool '{tool_name}' was rejected due to timeout waiting for human approval."
                
        if response_type == "choice":
            if response_value == "approve":
                return None  # Allow execution
            elif response_value == "reject":
                return f"Tool '{tool_name}' was rejected by human operator."
            elif response_value == "modify":
                # This would require more complex handling - for now, treat as approve
                return None
                
        if response_type == "text":
            # Human provided text feedback - could be instructions or modified args
            # For now, treat as approval with the text as context
            return None
            
        return None
    
    def _build_context(
        self,
        tool_name: str,
        tool_arguments: dict[str, Any],
        agent_name: str,
    ) -> str:
        """Build human-readable context for the checkpoint."""
        args_str = "\n".join(f"  {k}: {v!r}" for k, v in tool_arguments.items())
        return f"""Agent '{agent_name}' wants to execute tool: {tool_name}

Arguments:
{args_str}

Do you approve this action?"""
    
    async def on_turn_end(self, final_content: str | None, agent_name: str) -> None:
        """Clean up any pending checkpoints when turn ends."""
        await self._checkpoint_manager.abort_all()


class HITLConfig:
    """Configuration for HITL behavior."""
    
    # Tools that always require approval
    ALWAYS_REQUIRE_APPROVAL: list[str] = [
        "run_bash_cmd",
        "write_file",
        "replace_in_file",
        "apply_text_patch",
        "delete_file",
    ]
    
    # Tools that require approval when arguments match patterns
    CONDITIONAL_APPROVAL: dict[str, callable] = {
        # Example: require approval for bash commands with 'rm' or 'sudo'
        "run_bash_cmd": lambda args: any(
            dangerous in args.get("cmd", "").lower()
            for dangerous in ["rm -rf", "sudo", "chmod", "chown", "mkfs", "dd if"]
        ),
    }
```

---

## Phase 2: API Integration

### 2.1 New HTTP Endpoints (server/aiohttp_app.py)

Add these routes to `create_app()`:

```python
# HITL API endpoints
app.router.add_route("GET", "/api/hitl/checkpoints", list_checkpoints_handler)
app.router.add_route("POST", "/api/hitl/checkpoints/{checkpoint_id}/acknowledge", acknowledge_checkpoint_handler)
app.router.add_route("POST", "/api/hitl/checkpoints/{checkpoint_id}/respond", respond_to_checkpoint_handler)
app.router.add_route("POST", "/api/hitl/checkpoints/{checkpoint_id}/abort", abort_checkpoint_handler)
app.router.add_route("GET", "/api/hitl/checkpoints/stream", stream_checkpoint_events_handler)
```

### 2.2 Handler Implementations

```python
# server/hitl_handlers.py

from aiohttp import web
from pydantic import BaseModel, ValidationError

from sdk.hitl import get_checkpoint_manager
from sdk.events._models import (
    CheckpointStatePayload,
    HumanInputReceivedPayload,
)


class RespondRequest(BaseModel):
    response_type: str  # "text", "choice", "abort"
    response_value: str | None = None
    responder_id: str | None = None


async def list_checkpoints_handler(request: web.Request) -> web.Response:
    """List all checkpoints for a conversation."""
    conversation_id = request.query.get("conversation_id", "default")
    agent_id = request.query.get("agent_id")
    state = request.query.get("state")
    
    manager = get_checkpoint_manager(conversation_id)
    checkpoints = manager.list_checkpoints(
        agent_id=agent_id,
        state=CheckpointState[state.upper()] if state else None,
    )
    
    return web.json_response({
        "checkpoints": [
            {
                "checkpoint_id": c.checkpoint_id,
                "agent_id": c.agent_id,
                "state": c.state.name.lower(),
                "context": c.context,
                "options": c.options,
                "created_at": c.created_at.isoformat(),
                "acknowledged_at": c.acknowledged_at.isoformat() if c.acknowledged_at else None,
                "fulfilled_at": c.fulfilled_at.isoformat() if c.fulfilled_at else None,
            }
            for c in checkpoints
        ]
    })


async def acknowledge_checkpoint_handler(request: web.Request) -> web.Response:
    """Mark a checkpoint as acknowledged (human has seen it)."""
    checkpoint_id = request.match_info["checkpoint_id"]
    conversation_id = request.query.get("conversation_id", "default")
    
    manager = get_checkpoint_manager(conversation_id)
    success = await manager.acknowledge_checkpoint(checkpoint_id)
    
    if not success:
        return web.json_response({"error": "Checkpoint not found"}, status=404)
        
    return web.json_response({"ok": True})


async def respond_to_checkpoint_handler(request: web.Request) -> web.Response:
    """Provide human input for a checkpoint."""
    checkpoint_id = request.match_info["checkpoint_id"]
    conversation_id = request.query.get("conversation_id", "default")
    
    try:
        body = await request.json()
        req = RespondRequest(**body)
    except (json.JSONDecodeError, ValidationError) as e:
        return web.json_response({"error": f"Invalid request: {e}"}, status=400)
    
    manager = get_checkpoint_manager(conversation_id)
    checkpoint = manager.get_checkpoint(checkpoint_id)
    
    if not checkpoint:
        return web.json_response({"error": "Checkpoint not found"}, status=404)
        
    if checkpoint.state not in (CheckpointState.PENDING, CheckpointState.ACKNOWLEDGED):
        return web.json_response(
            {"error": f"Checkpoint already {checkpoint.state.name.lower()}"},
            status=409,
        )
    
    success = await manager.fulfill_checkpoint(
        checkpoint_id=checkpoint_id,
        response_type=req.response_type,
        response_value=req.response_value,
        responder_id=req.responder_id,
    )
    
    if not success:
        return web.json_response({"error": "Failed to fulfill checkpoint"}, status=500)
        
    return web.json_response({"ok": True})


async def abort_checkpoint_handler(request: web.Request) -> web.Response:
    """Abort a pending checkpoint."""
    checkpoint_id = request.match_info["checkpoint_id"]
    conversation_id = request.query.get("conversation_id", "default")
    
    manager = get_checkpoint_manager(conversation_id)
    success = await manager.fulfill_checkpoint(
        checkpoint_id=checkpoint_id,
        response_type="abort",
        response_value=None,
    )
    
    if not success:
        return web.json_response({"error": "Checkpoint not found"}, status=404)
        
    return web.json_response({"ok": True})


async def stream_checkpoint_events_handler(request: web.Request) -> web.StreamResponse:
    """SSE stream of checkpoint state changes."""
    conversation_id = request.query.get("conversation_id", "default")
    
    resp = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
    await resp.prepare(request)
    
    # Subscribe to checkpoint events for this conversation
    # Implementation would use the event dispatcher
    # ...
    
    return resp
```

---

## Phase 3: Tool Loop Integration

### 3.1 Modified Tool Execution (sdk/turn/_execution.py)

The `_run_tool_with_hooks` function needs to support async before_tool:

```python
async def _run_tool_with_hooks(
    tool_call: Any,
    tools: list[Callable[..., Any]],
    hooks: list[Any],
    hitl_hook: HITLHook | None = None,  # NEW
) -> dict[str, Any]:
    """Execute a single tool call with before/after hooks."""
    tool_name = tool_call.function.name
    tool_arguments = tool_call.function.arguments

    # Check HITL first (NEW)
    if hitl_hook and hitl_hook._tool_requires_approval(tool_name):
        intercepted = await hitl_hook.before_tool_async(tool_name, tool_arguments)
        if intercepted is not None:
            # Human rejected or modified - return the intercepted result
            return {
                "role": "tool",
                "tool_name": tool_name,
                "tool_call_id": tool_call.id,
                "content": intercepted,
            }

    # Standard hook processing
    intercepted = None
    for hook in hooks:
        fn = getattr(hook, "before_tool", None)
        if fn:
            intercepted = fn(tool_name, tool_arguments)
            if intercepted is not None:
                break

    if intercepted is not None:
        tool_result = intercepted
    else:
        tool_result = await _execute_tool_call(tool_name, tool_arguments, tools)

    for hook in hooks:
        fn = getattr(hook, "after_tool", None)
        if fn:
            tool_result = fn(tool_name, tool_arguments, tool_result)

    return {
        "role": "tool",
        "tool_name": tool_name,
        "tool_call_id": tool_call.id,
        "content": tool_result,
    }
```

### 3.2 Modified run_turn (sdk/turn/_execution.py)

```python
async def run_turn(
    history: ConversationHistory,
    agent: Agent,
    *,
    hooks: list[Any] | None = None,
    hitl_hook: HITLHook | None = None,  # NEW
) -> str | None:
    """Executes a single turn with HITL support."""
    # ... existing setup ...
    
    try:
        while True:
            iteration += 1
            # ... before_model hooks ...
            
            # ... model streaming ...
            
            # ... after_model hooks ...
            
            if not tool_calls:
                _publish_turn_end()
                return final_content

            # Execute tools with HITL support
            if parallel_cfg.enabled and len(tool_calls) > 1:
                # Parallel execution with HITL
                sem = asyncio.Semaphore(parallel_cfg.max_concurrent)

                async def _run_parallel(tc_item):
                    async with sem:
                        return tc_item, await _run_tool_with_hooks(
                            tc_item, tools, hooks, hitl_hook  # Pass HITL hook
                        )

                tasks = [asyncio.create_task(_run_parallel(tc)) for tc in tool_calls]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                # ... handle results ...
            else:
                # Sequential execution with HITL
                for tc in tool_calls:
                    result = await _run_tool_with_hooks(tc, tools, hooks, hitl_hook)
                    history.append(result)

    except StopRequestedError:
        # Abort all checkpoints on stop
        if hitl_hook:
            await hitl_hook._checkpoint_manager.abort_all()
        logger.info("Agent '%s' tool loop stopped by user request", agent.name)
        _publish_turn_end()
        raise
```

---

## Phase 4: Message Handler Integration

### 4.1 Modified _run_turn (server/message_handler.py)

```python
async def _run_turn(
    *,
    conversation: _Conversation,
    active_agent: Agent,
    user_content: str,
    options: LLMOptions,
    conversation_id: str | None,
    handler: Callable[[AgentEvent], object],
    hitl_config: HITLConfig | None = None,  # NEW
) -> None:
    """Execute a single conversation turn with HITL support."""
    # ... existing setup ...
    
    # Create HITL hook if configured (NEW)
    hitl_hook = None
    if hitl_config and hitl_config.enabled:
        from sdk.hitl import HITLHook
        hitl_hook = HITLHook(
            conversation_id=conv_id,
            require_approval_for=hitl_config.require_approval_for,
            require_approval_patterns=hitl_config.require_approval_patterns,
            default_timeout=hitl_config.default_timeout,
            auto_approve_on_timeout=hitl_config.auto_approve_on_timeout,
        )

    async with turn_scope(handler=handler, conversation_id=conversation_id):
        # ... existing setup ...
        
        hooks = default_hooks(
            active_agent,
            max_iterations=active_agent.max_iterations,
            ctx_manager=ctx_manager,
        )
        
        # Add HITL hook to the chain (NEW)
        if hitl_hook:
            hooks.append(hitl_hook)

        with suppress(StopRequestedError):
            await run_turn(
                history=conversation.history,
                agent=active_agent,
                hooks=hooks,
                hitl_hook=hitl_hook,  # Pass HITL hook
            )
        
        # Cleanup HITL on turn end (NEW)
        if hitl_hook:
            from sdk.hitl import remove_checkpoint_manager
            remove_checkpoint_manager(conv_id)
```

---

## Phase 5: Frontend Integration

### 5.1 New Event Handlers (Frontend)

```typescript
// Frontend event handler additions

interface HumanInputRequestPayload {
  type: "human_input_request";
  checkpoint_id: string;
  agent_id: string;
  context: string;
  options?: Array<{
    id: string;
    label: string;
    style?: "primary" | "secondary" | "danger";
  }>;
  timeout_seconds: number;
  blocking_tools?: string[];
}

interface HumanInputReceivedPayload {
  type: "human_input_received";
  checkpoint_id: string;
  response_type: "text" | "choice" | "abort" | "timeout";
  response_value?: string;
}

// Event handler in chat component
function handleAgentEvent(event: AgentEvent) {
  switch (event.payload.type) {
    case "human_input_request":
      showCheckpointModal(event.payload);
      break;
    case "human_input_received":
      hideCheckpointModal(event.payload.checkpoint_id);
      break;
    case "checkpoint_state":
      updateCheckpointStatus(event.payload);
      break;
    // ... existing handlers ...
  }
}

// Checkpoint modal component
function CheckpointModal({ checkpoint }: { checkpoint: HumanInputRequestPayload }) {
  const [timeLeft, setTimeLeft] = useState(checkpoint.timeout_seconds);
  
  useEffect(() => {
    if (checkpoint.timeout_seconds > 0) {
      const timer = setInterval(() => {
        setTimeLeft(t => Math.max(0, t - 1));
      }, 1000);
      return () => clearInterval(timer);
    }
  }, []);
  
  const respond = async (responseType: string, value?: string) => {
    await fetch(`/api/hitl/checkpoints/${checkpoint.checkpoint_id}/respond`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        response_type: responseType,
        response_value: value,
        responder_id: "user", // Could be actual user ID
      }),
    });
  };
  
  return (
    <Modal>
      <h3>Approval Required</h3>
      <div className="checkpoint-context">
        <pre>{checkpoint.context}</pre>
      </div>
      {checkpoint.timeout_seconds > 0 && (
        <div className="timeout-warning">
          Time remaining: {timeLeft}s
        </div>
      )}
      <div className="checkpoint-actions">
        {checkpoint.options?.map(opt => (
          <button
            key={opt.id}
            className={`btn btn-${opt.style}`}
            onClick={() => respond("choice", opt.id)}
          >
            {opt.label}
          </button>
        ))}
        <button onClick={() => respond("abort")}>Abort</button>
      </div>
    </Modal>
  );
}
```

---

## Multi-Agent Plan

### Agent 1: Core Infrastructure Agent
**Scope**: Implement the foundational HITL components

**Tasks**:
1. Create `sdk/hitl/` package structure
2. Implement `HumanInputRequestPayload`, `HumanInputReceivedPayload`, `CheckpointStatePayload` in `sdk/events/_models.py`
3. Implement `Checkpoint` dataclass and `CheckpointManager` in `sdk/hitl/_checkpoint.py`
4. Write unit tests for checkpoint manager

**Integration Points**:
- `sdk/events/_models.py` - Add new payload types to union
- `sdk/events/__init__.py` - Export new payload types

**Deliverables**:
- `sdk/hitl/__init__.py` with exports
- `sdk/hitl/_checkpoint.py` with full implementation
- `tests/sdk/hitl/test_checkpoint.py` with unit tests

---

### Agent 2: Hook Integration Agent
**Scope**: Implement HITL hook and tool loop integration

**Tasks**:
1. Implement `HITLHook` class in `sdk/hitl/_hook.py`
2. Modify `sdk/turn/_execution.py` to support async before_tool
3. Add HITL hook parameter to `run_turn()`
4. Handle StopRequestedError cleanup in HITL

**Integration Points**:
- `sdk/turn/_execution.py` - `_run_tool_with_hooks()` and `run_turn()`
- `sdk/hooks/__init__.py` - Export HITLHook
- `sdk/hitl/__init__.py` - Export HITLHook and HITLConfig

**Deliverables**:
- `sdk/hitl/_hook.py` with full implementation
- Modified `sdk/turn/_execution.py`
- `tests/sdk/hitl/test_hook.py` with unit tests

---

### Agent 3: HTTP API Agent
**Scope**: Implement REST API endpoints for HITL

**Tasks**:
1. Create `server/hitl_handlers.py` with all handlers
2. Add routes to `server/aiohttp_app.py`
3. Implement SSE streaming for checkpoint events
4. Add request/response validation with Pydantic

**Integration Points**:
- `server/aiohttp_app.py` - Add routes in `create_app()`
- `server/hitl_handlers.py` - New file

**Deliverables**:
- `server/hitl_handlers.py` with all handlers
- Modified `server/aiohttp_app.py` with routes
- `tests/server/test_hitl_handlers.py` with integration tests

---

### Agent 4: Message Handler Integration Agent
**Scope**: Wire HITL into the main message flow

**Tasks**:
1. Modify `server/message_handler.py` to accept HITL config
2. Create HITLHook instance in `_run_turn()`
3. Pass HITL hook to `run_turn()`
4. Cleanup checkpoint manager on turn end
5. Add HITL configuration to LLMOptions or separate config

**Integration Points**:
- `server/message_handler.py` - `_run_turn()` and `handle_user_message()`
- `agents/types.py` - Add HITLConfig to LLMOptions or new type

**Deliverables**:
- Modified `server/message_handler.py`
- Modified `agents/types.py` (if needed)
- `tests/server/test_message_handler_hitl.py` with tests

---

### Agent 5: Frontend Agent
**Scope**: Implement UI components for HITL

**Tasks**:
1. Add new event payload types to frontend TypeScript definitions
2. Create CheckpointModal component
3. Add checkpoint status indicator to chat UI
4. Implement checkpoint API client functions
5. Add visual distinction for human-approved vs auto-executed tools

**Integration Points**:
- Frontend event handling system
- Existing chat UI components

**Deliverables**:
- TypeScript type definitions
- CheckpointModal component
- API client functions
- Updated chat UI with checkpoint indicators

---

## File Structure

```
computron_9000/
├── sdk/
│   ├── hitl/                          # NEW PACKAGE
│   │   ├── __init__.py                  # Exports: CheckpointManager, HITLHook, HITLConfig, etc.
│   │   ├── _checkpoint.py               # Checkpoint dataclass and CheckpointManager
│   │   ├── _hook.py                     # HITLHook implementation
│   │   └── _config.py                   # HITLConfig and defaults
│   ├── events/
│   │   ├── _models.py                   # MODIFIED: Add HITL payload types
│   │   └── __init__.py                  # MODIFIED: Export new payloads
│   └── turn/
│       └── _execution.py                # MODIFIED: HITL hook support
├── server/
│   ├── hitl_handlers.py                 # NEW: HTTP handlers for HITL API
│   ├── aiohttp_app.py                   # MODIFIED: Add HITL routes
│   └── message_handler.py               # MODIFIED: HITL integration
├── agents/
│   └── types.py                         # MODIFIED: Add HITLConfig
├── tests/
│   ├── sdk/
│   │   ├── hitl/                        # NEW: Test package
│   │   │   ├── test_checkpoint.py
│   │   │   ├── test_hook.py
│   │   │   └── __init__.py
│   │   └── events/
│   │       └── test_hitl_payloads.py    # NEW: Test new payloads
│   └── server/
│       ├── test_hitl_handlers.py        # NEW: API integration tests
│       └── test_message_handler_hitl.py # NEW: Message handler tests
└── server/ui/
    └── src/
        └── components/
            └── CheckpointModal.jsx        # NEW: Frontend component
```

---

## Configuration

Add to `config.yaml`:

```yaml
hitl:
  enabled: false                    # Master switch
  default_timeout: 300              # 5 minutes default timeout
  auto_approve_on_timeout: false    # Reject on timeout by default
  require_approval_for:             # Tools always requiring approval
    - run_bash_cmd
    - write_file
    - replace_in_file
    - apply_text_patch
  require_approval_patterns:        # Regex patterns for tool names
    - "^delete_.*"
    - "^dangerous_.*"
  conditional_approval:             # Conditional rules
    run_bash_cmd:
      dangerous_patterns:
        - "rm -rf"
        - "sudo"
        - "chmod"
        - "chown"
        - "mkfs"
        - "dd if"
```

---

## Security Considerations

1. **Authentication**: All HITL endpoints should require authentication
2. **Authorization**: Verify the responder has permission to approve for the conversation
3. **Audit Logging**: Log all checkpoint create/acknowledge/fulfill events
4. **Timeout Handling**: Prevent indefinite blocking of turns
5. **Concurrent Access**: Handle multiple humans viewing the same checkpoint

---

## Testing Strategy

### Unit Tests
- Checkpoint state machine transitions
- CheckpointManager concurrent operations
- HITLHook tool approval logic
- Timeout handling

### Integration Tests
- Full checkpoint lifecycle via API
- Concurrent checkpoint operations
- Turn stop with pending checkpoints
- Event streaming

### End-to-End Tests
- Frontend modal interaction
- Real-time checkpoint updates
- Multi-user scenarios

---

## Migration Path

1. **Phase 1**: Deploy core infrastructure (no UI changes)
2. **Phase 2**: Enable HITL via feature flag for specific agents
3. **Phase 3**: Full UI integration
4. **Phase 4**: Default enable for dangerous tools

---

## Summary

This design integrates Human-in-the-Loop capabilities into Computron 9000 by:

1. **Extending the event system** with new payload types for human input requests/responses
2. **Adding checkpoint management** to track and coordinate human approvals
3. **Creating a HITL hook** that intercepts tool calls requiring approval
4. **Exposing REST APIs** for frontend interaction with checkpoints
5. **Integrating with the turn lifecycle** for proper cleanup and state management

The design leverages existing patterns (events, hooks, turns) and maintains backward compatibility when HITL is disabled.
