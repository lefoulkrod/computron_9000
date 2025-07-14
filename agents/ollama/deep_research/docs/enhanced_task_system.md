# Enhanced Task Data System Architecture

This document defines the architecture for the enhanced task data system that enables coordinated multi-agent research workflows with structured data passing.

## System Overview

The enhanced task system provides:

1. **Structured Task Data**: Typed data structures for each agent with JSON schema support
2. **Centralized Storage**: In-memory task data storage with thread safety
3. **Coordinator-Only Creation**: Only the coordinator can create and delete tasks
4. **Agent Retrieval**: Agents can only retrieve their assigned task data
5. **Strong Typing**: Pydantic validation with clear type definitions
6. **JSON Schema Compliance**: All tools serializable for LLM understanding

## Core Components

### 1. Task Data Types (`shared/task_data_types.py`)

Pydantic models defining structured data for each agent type:

- **`BaseTaskData`**: Base class with common fields for all task types
- **`WebResearchTaskData`**: Web research parameters and configuration  
- **`SocialResearchTaskData`**: Social media research settings
- **`AnalysisTaskData`**: Analysis focus and source data
- **`SynthesisTaskData`**: Synthesis goals and research findings
- **`QueryDecompositionTaskData`**: Query decomposition strategy

### 2. Task Data Storage (`shared/task_data_storage.py`)

In-memory storage system for task data:

- **`TaskDataStorage`**: Singleton in-memory storage with thread safety
- **`store_task_data(task_data)`**: Store task data (coordinator only)
- **`retrieve_task_data(task_id)`**: Retrieve task data by ID
- **`delete_task_data(task_id)`**: Delete task data (coordinator only)

### 3. Agent Task Tools (`shared/agent_task_tools.py`)

Single tool function for agent task data access:

- **`get_task_data(task_id)`**: Agent tool for retrieving assigned task data
- **JSON schema compliant**: Tool fully serializable for agent understanding
- **Strongly typed returns**: Structured responses with error handling

### 4. Coordinator Tools (`coordinator/coordination_tools.py`)

Single automated workflow tool for coordinator:

- **`execute_deep_research_workflow()`**: Single entry point that executes the complete research workflow imperatively
- **`cleanup_completed_tasks()`**: Clean up completed tasks after workflow completion

Internal task creation methods (not exposed as tools):

- **`_create_web_research_task()`**: Internal method to create web research tasks
- **`_create_analysis_task()`**: Internal method to create analysis tasks  
- **`_create_social_research_task()`**: Internal method to create social research tasks
- **`_create_synthesis_task()`**: Internal method to create synthesis tasks
- **`_create_query_decomposition_task()`**: Internal method to create query decomposition tasks
- **`_execute_agent_with_task()`**: Internal method to execute agent with task ID

## Usage Patterns

### Coordinator Automated Workflow

```python
# Single tool executes complete deep research workflow
coordinator = CoordinationTools()

# Execute entire workflow with one call
result = coordinator.execute_deep_research_workflow(
    research_query="Impact of AI on employment markets",
    research_domains=["web", "social"],
    output_format="comprehensive_report"
)

# Workflow executes imperatively:
# 1. Creates and executes query decomposition task
# 2. Creates and executes web research tasks for each subquery  
# 3. Creates and executes social research tasks for each subquery
# 4. Creates and executes analysis task with all research results
# 5. Creates and executes synthesis task with analysis results
# 6. Cleans up all completed tasks
# 7. Returns final synthesized report
```

### Internal Workflow Execution (Automatic)

```python
# This logic is encoded in execute_deep_research_workflow():

def execute_deep_research_workflow(self, research_query: str, **options):
    workflow_id = f"deep_research_{uuid.uuid4().hex[:8]}"
    
    # Step 1: Query decomposition
    decomp_task_id = self._create_query_decomposition_task(
        workflow_id=workflow_id,
        original_query=research_query
    )
    decomp_result = self._execute_agent_with_task("query_decomposition", decomp_task_id)
    
    # Step 2: Execute research tasks for each subquery
    all_research_results = []
    for subquery in decomp_result["subqueries"]:
        # Web research
        web_task_id = self._create_web_research_task(
            workflow_id=workflow_id,
            research_query=subquery,
            related_queries=decomp_result["related_queries"]
        )
        web_result = self._execute_agent_with_task("web_research", web_task_id)
        all_research_results.append(web_result)
        
        # Social research
        social_task_id = self._create_social_research_task(
            workflow_id=workflow_id,
            research_query=subquery
        )
        social_result = self._execute_agent_with_task("social_research", social_task_id)
        all_research_results.append(social_result)
    
    # Step 3: Analysis of all findings
    analysis_task_id = self._create_analysis_task(
        workflow_id=workflow_id,
        analysis_focus="Cross-reference findings for consistency and conflicts",
        sources_to_analyze=all_research_results
    )
    analysis_result = self._execute_agent_with_task("analysis", analysis_task_id)
    
    # Step 4: Final synthesis
    synthesis_task_id = self._create_synthesis_task(
        workflow_id=workflow_id,
        synthesis_goal="Comprehensive research report",
        analysis_results=[analysis_result],
        research_findings=all_research_results
    )
    final_result = self._execute_agent_with_task("synthesis", synthesis_task_id)
    
    # Step 5: Cleanup
    self.cleanup_completed_tasks(workflow_id)
    
    return final_result
```

### Agent Task Retrieval (Mandatory Pattern)

All agents MUST follow this pattern as their first action:

```python
# Agent receives: "Your task ID is: web_research_001_abc123"

# Step 1: ALWAYS retrieve task data first (required)
task_response = get_task_data("web_research_001_abc123")

# Step 2: Parse and validate task data
if task_response["success"]:
    task_data = task_response["task_data"]
    research_query = task_data["research_query"]
    source_types = task_data["source_types"] 
    max_sources = task_data["max_sources"]
    # ... use structured configuration
else:
    # Return error - cannot proceed without task data
    return task_response["error_message"]
```



## Agent Integration Requirements

### Required Changes for All Agents

1. **Add single task data tool**:
   ```python
   from ..shared.agent_task_tools import get_task_data
   
   # Add to agent tools list (only tool needed)
   tools=[
       get_task_data,  # REQUIRED: Single task retrieval tool
       # ... existing agent-specific tools
   ]
   ```

2. **Update agent prompts (MANDATORY)**:
   ```python
   AGENT_PROMPT = """
   # CRITICAL: Task Data Retrieval - FIRST ACTION REQUIRED
   
   If your instruction contains a task ID (format: "Your task ID is: <task_id>"):
   1. IMMEDIATELY call get_task_data(<task_id>) as your FIRST action
   2. Parse the returned task_data to understand your requirements
   3. Use the structured configuration for all subsequent work
   4. If task data retrieval fails, return the error immediately
   
   NEVER proceed without first retrieving task data when a task ID is provided.
   
   # ... rest of agent-specific prompt
   """
   ```

### Agent Workflow (Mandatory Pattern)

1. **Check for task ID** in instructions
2. **Call `get_task_data(task_id)`** as FIRST action if task ID present
3. **Parse and validate** task data before proceeding
4. **Use structured configuration** for all work
5. **Return structured results** for coordinator processing

## Task Data Structures

### BaseTaskData

```python
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

class BaseTaskData(BaseModel):
    """Base class for all agent task data."""
    
    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    workflow_id: str = Field(..., description="Parent workflow identifier") 
    agent_type: str = Field(..., description="Target agent type")
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    context: dict[str, Any] = Field(default_factory=dict)
```

### WebResearchTaskData

```python
class WebResearchTaskData(BaseTaskData):
    """Structured data for web research tasks."""
    
    research_query: str = Field(..., min_length=1)
    source_types: list[str] = Field(default=["academic", "news", "official"])
    max_sources: int = Field(default=10, ge=1, le=50) 
    previous_findings: list[dict[str, Any]] = Field(default_factory=list)
    related_queries: list[str] = Field(default_factory=list)
    agent_type: str = Field(default="web_research", frozen=True)
```

### AnalysisTaskData

```python
class AnalysisTaskData(BaseTaskData):
    """Structured data for analysis tasks."""
    
    analysis_focus: str = Field(..., min_length=1)
    sources_to_analyze: list[dict[str, Any]] = Field(...)
    web_research_results: list[dict[str, Any]] = Field(default_factory=list)
    social_research_results: list[dict[str, Any]] = Field(default_factory=list)
    analysis_types: list[str] = Field(default=["consistency", "conflicts"])
    agent_type: str = Field(default="analysis", frozen=True)
```

### SocialResearchTaskData

```python
class SocialResearchTaskData(BaseTaskData):
    """Structured data for social media research tasks."""
    
    research_query: str = Field(..., min_length=1)
    platforms: list[str] = Field(default=["reddit"])
    max_posts: int = Field(default=20, ge=1, le=100)
    time_range: str = Field(default="week")
    sentiment_analysis: bool = Field(default=True)
    previous_findings: list[dict[str, Any]] = Field(default_factory=list)
    agent_type: str = Field(default="social_research", frozen=True)
```

### SynthesisTaskData

```python
class SynthesisTaskData(BaseTaskData):
    """Structured data for synthesis tasks."""
    
    synthesis_goal: str = Field(..., min_length=1)
    analysis_results: list[dict[str, Any]] = Field(...)
    research_findings: list[dict[str, Any]] = Field(default_factory=list)
    output_format: str = Field(default="comprehensive_report")
    include_sources: bool = Field(default=True)
    agent_type: str = Field(default="synthesis", frozen=True)
```

### QueryDecompositionTaskData

```python
class QueryDecompositionTaskData(BaseTaskData):
    """Structured data for query decomposition tasks."""
    
    original_query: str = Field(..., min_length=1)
    complexity_level: int = Field(default=3, ge=1, le=5)
    max_subqueries: int = Field(default=5, ge=1, le=10)
    research_domains: list[str] = Field(default=["web", "social"])
    agent_type: str = Field(default="query_decomposition", frozen=True)
```

## Architecture Principles

### 1. Coordinator-Only Task Management
- Only the coordinator can create and delete tasks
- Agents cannot create, modify, or delete tasks  
- Single automated workflow tool handles complete research process
- All complex data flows through coordinator-managed tasks

### 2. Agent Task Retrieval Pattern
- Agents have one task tool: `get_task_data(task_id)`
- Must retrieve task data as first action when task ID provided
- Agents can only read their assigned task data

### 3. Strongly Typed Data Structures
- All task data validated with Pydantic models
- Each agent type has its own task data structure
- All structures serializable to JSON schema

### 4. Simple Storage Model
- In-memory storage with thread safety
- Task ID based access
- Minimal complexity for maximum reliability


## Benefits

### For Agents
- Single tool needed: `get_task_data(task_id)`
- Rich context with structured configuration
- Clear mandatory pattern for task data retrieval

### For Coordinator
- Single automated workflow tool eliminates LLM decision complexity
- Complete task creation and lifecycle management
- Centralized task data prevents agent communication
- Imperative workflow execution ensures consistent results

### For Development
- Mandatory patterns ensure reliable behavior
- All tools JSON schema serializable
- Clean separation of responsibilities

## Tool Function Schemas

### Agent Task Tool (JSON Schema Compliant)

```python
# get_task_data tool schema
{
    "name": "get_task_data",
    "description": "Retrieve structured task data. MUST be called first if task ID provided.",
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "The task ID provided in your instructions"
            }
        },
        "required": ["task_id"]
    }
}
```

### Response Schemas

```python
# Successful task data response
{
    "success": true,
    "task_data": {
        "task_id": "web_research_001_abc123",
        "workflow_id": "research_001", 
        "agent_type": "web_research",
        "research_query": "Latest AI safety research",
        "source_types": ["academic", "official"],
        "max_sources": 15,
        "previous_findings": [],
        "related_queries": [],
        "created_at": "2025-01-15T10:30:00Z",
        "context": {}
    },
    "error_message": null,
    "agent_type": "web_research"
}

# Error response
{
    "success": false,
    "task_data": null,
    "error_message": "Task not found: invalid_task_id",
    "agent_type": null
}
```

### Coordinator Tool Schemas

```python
# execute_deep_research_workflow tool schema
{
    "name": "execute_deep_research_workflow",
    "description": "Execute complete automated deep research workflow with all agents",
    "parameters": {
        "type": "object",
        "properties": {
            "research_query": {
                "type": "string",
                "description": "The main research question to investigate"
            },
            "research_domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Research domains to include (web, social)",
                "default": ["web", "social"]
            },
            "output_format": {
                "type": "string", 
                "description": "Format for final report",
                "default": "comprehensive_report"
            }
        },
        "required": ["research_query"]
    }
}

# execute_deep_research_workflow response
{
    "success": true,
    "workflow_id": "deep_research_001_abc123",
    "final_report": {...},
    "execution_summary": {
        "query_decomposition": "completed",
        "web_research_tasks": 3,
        "social_research_tasks": 3, 
        "analysis_completed": true,
        "synthesis_completed": true,
        "total_sources_analyzed": 45
    },
    "message": "Deep research workflow completed successfully"
}
```
