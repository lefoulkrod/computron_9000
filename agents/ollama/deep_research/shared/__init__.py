"""Shared infrastructure for the Deep Research multi-agent system.

This module contains internal infrastructure components used across the
deep_research package. These are not intended for external use.
"""

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
from .source_tracker_utils import (
    clear_workflow_sources,
    create_agent_source_tracker,
    export_workflow_sources,
    get_workflow_source_summary,
    import_workflow_sources,
)
from .source_tracking import (
    AgentSourceTracker,
    SharedSourceRegistry,
    SourceAccess,
)
from .storage import WorkflowStorage, get_storage
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

# Internal module - exports are available for use within deep_research package only
__all__ = [
    # Core types
    "AgentTask",
    "AgentResult",
    "ResearchWorkflow",
    # Storage and coordination
    "WorkflowStorage",
    "MessageBus",
    "ResearchWorkflowCoordinator",
    # Logging infrastructure
    "setup_multi_agent_logging",
    "MultiAgentError",
    "AgentTaskError",
    "WorkflowCoordinationError",
    "SourceTrackingError",
    # Source tracking
    "AgentSourceTracker",
    "SharedSourceRegistry",
    "SourceAccess",
    # Configuration
    "AgentConfig",
    "MultiAgentConfigManager",
    "get_agent_config",
    "register_custom_agent_config",
    # Tool interface
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
    # Utility functions
    "clear_workflow_sources",
    "create_agent_source_tracker",
    "export_workflow_sources",
    "get_workflow_source_summary",
    "import_workflow_sources",
    "get_storage",
]
