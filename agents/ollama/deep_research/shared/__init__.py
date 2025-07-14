"""Shared infrastructure for the Deep Research multi-agent system.

This module contains internal infrastructure components used across the
deep_research package. These are not intended for external use.
"""

from .agent_task_tools import (
    get_analysis_task_data,
    get_query_decomposition_task_data,
    get_social_research_task_data,
    get_synthesis_task_data,
    get_task_data,
    get_web_research_task_data,
)
from .communication import MessageBus
from .logging_infrastructure import (
    AgentTaskError,
    MultiAgentError,
    WorkflowCoordinationError,
    setup_multi_agent_logging,
)
from .task_data_storage import (
    TaskDataStorage,
    clear_workflow_tasks,
    delete_task_data,
    get_task_data_storage,
    retrieve_task_data,
    store_task_data,
)
from .task_data_types import (
    TASK_DATA_TYPES,
    AnalysisTaskData,
    BaseTaskData,
    QueryDecompositionTaskData,
    SocialResearchTaskData,
    SynthesisTaskData,
    WebResearchTaskData,
    create_task_data,
    validate_task_data,
)
from .types import (
    CredibilityAssessment,
    ResearchCitation,
    ResearchSource,
    SourceCategorization,
    WebpageMetadata,
)

# Internal module - exports are available for use within deep_research package only
__all__ = [
    # Task data system
    "BaseTaskData",
    "WebResearchTaskData",
    "SocialResearchTaskData",
    "AnalysisTaskData",
    "SynthesisTaskData",
    "QueryDecompositionTaskData",
    "TASK_DATA_TYPES",
    "create_task_data",
    "validate_task_data",
    # Task data storage
    "TaskDataStorage",
    "get_task_data_storage",
    "store_task_data",
    "retrieve_task_data",
    "delete_task_data",
    "clear_workflow_tasks",
    # Agent task tools
    "get_task_data",
    "get_web_research_task_data",
    "get_social_research_task_data",
    "get_analysis_task_data",
    "get_synthesis_task_data",
    "get_query_decomposition_task_data",
    # Communication
    "MessageBus",
    # Logging infrastructure
    "setup_multi_agent_logging",
    "MultiAgentError",
    "AgentTaskError",
    "WorkflowCoordinationError",
    # Configuration has been removed - agents now use main app config
    # Research types (kept for future use)
    "ResearchSource",
    "ResearchCitation",
    "CredibilityAssessment",
    "SourceCategorization",
    "WebpageMetadata",
]
