"""
Deep Research Agent package.

This module provides a multi-agent system for conducting thorough research
across multiple sources to provide comprehensive, well-sourced answers to
complex queries.

The system includes specialized agents for different research tasks:
- Research Coordinator Agent: Orchestrates multi-agent workflows
- Query Decomposition Agent: Breaks down complex queries
- Web Research Agent: Conducts web-based research
- Social Research Agent: Analyzes social media and forums
- Analysis Agent: Performs source credibility assessment
- Synthesis Agent: Combines findings into comprehensive reports
"""

# Legacy single-agent interface (maintained for backward compatibility)
from .agent import (
    deep_research_agent,
    deep_research_agent_after_callback,
    deep_research_agent_before_callback,
    deep_research_agent_tool,
    get_citation_practices,
    get_tool_documentation,
    search_tool_documentation,
    source_tracker,
)

# Multi-agent system components
from .coordinator import (
    CoordinationTools,
    ConcreteResearchWorkflowCoordinator,
    coordination_tools,
    research_coordinator_agent,
    research_coordinator_after_callback,
    research_coordinator_before_callback,
    research_coordinator_tool,
)
from .query_decomposition import (
    query_decomposition_agent,
    query_decomposition_tool,
)

# Shared infrastructure
from .shared import (
    AgentConfig,
    AgentResult,
    AgentSourceTracker,
    AgentTask,
    AgentTool,
    AnalysisTool,
    MessageBus,
    MultiAgentConfigManager,
    ResearchWorkflow,
    ResearchWorkflowCoordinator,
    SharedSourceRegistry,
    SocialResearchTool,
    StandardErrorHandling,
    SynthesisTool,
    ToolRegistry,
    WebResearchTool,
    WorkflowStorage,
    get_agent_config,
    get_tool_registry,
    register_agent_tool,
    register_custom_agent_config,
)
from .shared.logging_infrastructure import (
    AgentTaskError,
    MultiAgentError,
    WorkflowCoordinationError,
    setup_multi_agent_logging,
)
from .analysis import (
    analysis_agent,
    analysis_tool,
)
from .social_research import (
    social_research_agent,
    social_research_tool,
)
from .synthesis import (
    synthesis_agent,
    synthesis_tool,
)
from .web_research import (
    web_research_agent,
    web_research_tool,
)

__all__ = [
    # Legacy single-agent interface (backward compatibility)
    "deep_research_agent",
    "deep_research_agent_before_callback", 
    "deep_research_agent_after_callback",
    "deep_research_agent_tool",
    "source_tracker",
    "get_tool_documentation",
    "search_tool_documentation", 
    "get_citation_practices",
    # Research Coordinator (Phase 3.1.3)
    "research_coordinator_agent",
    "research_coordinator_before_callback",
    "research_coordinator_after_callback",
    "research_coordinator_tool",
    "coordination_tools",
    "CoordinationTools",
    "ConcreteResearchWorkflowCoordinator",
    # Multi-agent system (other agents)
    "query_decomposition_agent",
    "query_decomposition_tool",
    "web_research_agent",
    "web_research_tool",
    "social_research_agent",
    "social_research_tool",
    "analysis_agent",
    "analysis_tool",
    "synthesis_agent",
    "synthesis_tool",
    # Shared infrastructure
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
    # Source tracking infrastructure
    "AgentSourceTracker",
    "SharedSourceRegistry",
    # Configuration management
    "AgentConfig",
    "MultiAgentConfigManager",
    "get_agent_config",
    "register_custom_agent_config",
    # Tool interface infrastructure
    "AgentTool",
    "WebResearchTool",
    "SocialResearchTool",
    "AnalysisTool",
    "SynthesisTool",
    "ToolRegistry",
    "StandardErrorHandling",
    "get_tool_registry",
    "register_agent_tool",
]
