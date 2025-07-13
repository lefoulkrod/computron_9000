"""Shared infrastructure for the Deep Research multi-agent system."""

from .agent_config import (
    AgentConfig,
    MultiAgentConfigManager,
    get_agent_config,
    register_custom_agent_config,
)
from .communication import MessageBus
from .logging_infrastructure import (
    AgentTaskError,
    MultiAgentError,
    SourceTrackingError,
    WorkflowCoordinationError,
    setup_multi_agent_logging,
)
from .source_tracking import (
    AgentSourceTracker,
    SharedSourceRegistry,
    SourceAccess,
)
from .storage import WorkflowStorage
from .tool_interface import (
    AgentTool,
    AnalysisTool,
    SocialResearchTool,
    StandardErrorHandling,
    SynthesisTool,
    ToolRegistry,
    ToolResult,
    WebResearchTool,
    get_tool_registry,
    register_agent_tool,
)
from .types import AgentResult, AgentTask, ResearchWorkflow
from .workflow_coordinator import ResearchWorkflowCoordinator

__all__ = [
    "AgentTask",
    "AgentResult",
    "ResearchWorkflow",
    "WorkflowStorage",
    "MessageBus",
    "ResearchWorkflowCoordinator",
    "setup_multi_agent_logging",
    "MultiAgentError",
    "AgentTaskError",
    "WorkflowCoordinationError",
    "SourceTrackingError",
    "AgentSourceTracker",
    "SharedSourceRegistry",
    "SourceAccess",
    "AgentConfig",
    "MultiAgentConfigManager",
    "get_agent_config",
    "register_custom_agent_config",
    "AgentTool",
    "WebResearchTool",
    "SocialResearchTool",
    "AnalysisTool",
    "SynthesisTool",
    "ToolRegistry",
    "ToolResult",
    "StandardErrorHandling",
    "get_tool_registry",
    "register_agent_tool",
]
