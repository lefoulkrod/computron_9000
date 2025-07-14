# Multi-Agent Architecture for Deep Research

## Architecture Overview

The deep research system is redesigned as a **multi-agent workflow** to manage complexity, context limits, and specialized tasks. The architecture consists of:

1. **Research Coordinator Agent** - Orchestrates the entire research process
2. **Query Decomposition Agent** - Breaks down complex queries into sub-queries
3. **Web Research Agent** - Specialized for web-based research tasks
4. **Social Research Agent** - Focused on social media and forum research
5. **Analysis Agent** - Performs source analysis and credibility assessment
6. **Synthesis Agent** - Combines findings and generates reports

## Key Benefits

- **Context Management**: Each agent maintains manageable context sizes
- **Specialization**: Optimized agents for specific research tasks
- **Scalability**: Parallel processing of research tasks
- **Maintainability**: Smaller, focused codebases
- **Flexibility**: Easy to add new specialized agents or modify existing ones

## System Components

### Multi-Agent System Components

1. **Research Coordinator Agent** (refactored from current Deep Research Agent)
2. **Query Decomposition Agent** 
3. **Web Research Agent**
4. **Social Research Agent**
5. **Analysis Agent**
6. **Synthesis Agent**
7. **Workflow Coordinator Infrastructure**
8. **Shared Data Storage System**

### Legacy Tool Distribution
- **Citation Manager** → Integrated into Web and Social Research Agents
- **Credibility Evaluator** → Moved to Analysis Agent
- **Research Planner** → Split between Coordinator and Query Decomposition Agents
- **Cross-Reference Verifier** → Moved to Analysis Agent
- **Knowledge Graph Builder** → Moved to Synthesis Agent

## Agent Responsibilities and Context Management

### 1. Research Coordinator Agent (Current Deep Research Agent - Refactored)
**Role**: Orchestrates the multi-agent workflow and maintains overall research state
**Context Size**: Medium (manages workflow state, not detailed content)
**Responsibilities**:
- Receives initial research requests
- Delegates tasks to specialized agents
- Tracks overall research progress
- Coordinates between agents
- Generates final research reports
- Manages inter-agent communication

### 2. Query Decomposition Agent
**Role**: Breaks down complex queries into manageable sub-queries
**Context Size**: Small (focused on query analysis only)
**Responsibilities**:
- Analyzes complex research questions
- Identifies key subtopics and dependencies
- Creates prioritized research plans
- Suggests research strategies
- Refines queries based on initial results

### 3. Web Research Agent
**Role**: Performs web-based research tasks
**Context Size**: Medium (manages web sources and content)
**Responsibilities**:
- Executes Google searches
- Retrieves and analyzes web pages
- Extracts key information from web sources
- Maintains web source tracking
- Performs basic credibility assessment of web sources

### 4. Social Research Agent
**Role**: Specializes in social media and forum research
**Context Size**: Medium (manages social content and discussions)
**Responsibilities**:
- Conducts Reddit searches and analysis
- Analyzes comment sentiment and consensus
- Evaluates social source credibility
- Tracks discussion threads and user interactions
- Identifies trending topics and public opinion

### 5. Analysis Agent
**Role**: Performs deep analysis of sources and content
**Context Size**: Large (needs access to multiple sources for comparison)
**Responsibilities**:
- Conducts comprehensive source credibility assessment
- Performs cross-reference verification
- Detects inconsistencies between sources
- Extracts and analyzes metadata
- Categorizes sources by type and reliability

### 6. Synthesis Agent
**Role**: Combines findings from all agents into coherent reports
**Context Size**: Large (needs access to all research findings)
**Responsibilities**:
- Synthesizes information from multiple sources
- Generates comprehensive summaries
- Creates citation lists and bibliographies
- Identifies knowledge gaps and contradictions
- Produces final research reports

## Communication Infrastructure

### Pydantic Models

```python
class AgentTask(pydantic.BaseModel):
    """Represents a task assigned to a specific agent."""
    task_id: str
    agent_type: str  # query_decomposition, web_research, social_research, analysis, synthesis
    task_type: str  # decompose_query, search_web, analyze_sources, synthesize_findings
    input_data: Dict[str, Any]
    priority: int = 5
    dependencies: List[str] = []
    status: str = "pending"  # pending, in_progress, completed, failed
    created_at: str
    assigned_at: Optional[str] = None
    completed_at: Optional[str] = None

class AgentResult(pydantic.BaseModel):
    """Represents the result from an agent task."""
    task_id: str
    agent_type: str
    result_data: Dict[str, Any]
    success: bool
    error_message: Optional[str] = None
    sources_used: List[str] = []
    follow_up_tasks: List[AgentTask] = []
    completion_time: str

class ResearchWorkflow(pydantic.BaseModel):
    """Represents the overall research workflow state."""
    workflow_id: str
    original_query: str
    current_phase: str  # decomposition, research, analysis, synthesis
    active_tasks: List[AgentTask] = []
    completed_tasks: List[AgentResult] = []
    workflow_state: Dict[str, Any] = {}
    created_at: str
    updated_at: str
```

### Workflow Coordinator

```python
class ResearchWorkflowCoordinator:
    """Coordinates multi-agent research workflow."""
    
    async def start_research_workflow(self, query: str) -> str:
        """Initiate a new research workflow."""
        
    async def assign_task_to_agent(self, task: AgentTask) -> str:
        """Assign a task to the appropriate specialized agent."""
        
    async def process_agent_result(self, result: AgentResult) -> List[AgentTask]:
        """Process results from an agent and generate follow-up tasks."""
        
    async def get_workflow_status(self, workflow_id: str) -> Dict[str, Any]:
        """Get current status of a research workflow."""
```

## Directory Structure

```
agents/ollama/deep_research/
├── __init__.py
├── coordinator/
│   ├── __init__.py
│   ├── agent.py              # Main coordinator agent
│   ├── workflow_coordinator.py
│   └── prompt.py
├── query_decomposition/
│   ├── __init__.py
│   ├── agent.py
│   ├── decomposer.py
│   └── prompt.py
├── web_research/
│   ├── __init__.py
│   ├── agent.py
│   ├── web_tools.py
│   └── prompt.py
├── social_research/
│   ├── __init__.py
│   ├── agent.py
│   ├── social_tools.py
│   └── prompt.py
├── analysis/
│   ├── __init__.py
│   ├── agent.py
│   ├── analysis_tools.py
│   └── prompt.py
├── synthesis/
│   ├── __init__.py
│   ├── agent.py
│   ├── synthesis_tools.py
│   └── prompt.py
└── shared/
    ├── __init__.py
    ├── types.py              # Shared type definitions
    ├── communication.py      # Inter-agent communication
    └── storage.py           # Shared data storage
```

## Workflow Implementation Strategy

### Workflow Phases

1. **Phase 1: Query Decomposition**
   - Coordinator receives initial query
   - Assigns decomposition task to Query Decomposition Agent
   - Query Decomposition Agent breaks down query into sub-queries
   - Returns prioritized research plan to Coordinator

2. **Phase 2: Parallel Research Execution**
   - Coordinator assigns sub-queries to Web Research and Social Research Agents
   - Agents work in parallel on different sub-queries
   - Each agent maintains its own source tracking
   - Results are returned to Coordinator as they complete

3. **Phase 3: Source Analysis**
   - Coordinator assigns collected sources to Analysis Agent
   - Analysis Agent performs credibility assessment and cross-referencing
   - Returns analysis results and quality scores

4. **Phase 4: Synthesis and Reporting**
   - Coordinator compiles all results and assigns to Synthesis Agent
   - Synthesis Agent creates comprehensive report
   - Final report returned to user through Coordinator

## Context Management Strategy

**Problem**: Individual agents will have focused contexts, avoiding overload
**Solutions**:

1. **Task-Specific Context**: Each agent only receives context relevant to its specific task
2. **Shared Storage**: Common storage for research findings accessible by workflow ID
3. **Summary Passing**: Agents pass summaries rather than full content between tasks
4. **Lazy Loading**: Agents only load detailed content when specifically needed
5. **Context Cleanup**: Agents clear context after task completion

## Inter-Agent Communication Patterns

**Communication Methods**:

1. **Task Queue Pattern**: Coordinator maintains task queues for each agent type
2. **Result Callback Pattern**: Agents return results to Coordinator with follow-up tasks
3. **Shared State Pattern**: Common workflow state accessible by workflow ID
4. **Event-Driven Pattern**: Agents emit events for workflow state changes

## Supporting Infrastructure

### Workflow Coordinator
- Manages task assignment and scheduling
- Tracks workflow state and progress
- Handles inter-agent communication
- Provides workflow status reporting

### Shared Data Storage
- Centralized storage for research findings
- Source tracking across multiple agents
- Workflow state persistence
- Context management for large datasets
