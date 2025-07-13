"""
Inter-agent communication tools for the Deep Research Agent.

This module provides tools for the legacy Deep Research Agent to 
communicate with and delegate to the new multi-agent system.
"""

import json
import logging

from .coordinator import CoordinationTools

logger = logging.getLogger(__name__)

# Initialize coordination tools for delegation
_coordination_tools = CoordinationTools("deep_research_delegate")


def delegate_to_multi_agent_research(query: str) -> str:
    """
    Delegate complex research queries to the multi-agent research system.
    
    This tool allows the legacy Deep Research Agent to leverage the new
    multi-agent system for complex research that would benefit from
    specialized agent coordination.
    
    Args:
        query: The research query to delegate to the multi-agent system
        
    Returns:
        JSON string with delegation results and workflow information
    """
    try:
        # Use the coordination tools to initiate a workflow
        import asyncio
        import concurrent.futures
        import threading
        
        def run_async_in_thread():
            """Run the async function in a separate thread with its own event loop."""
            try:
                # Create a new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        _coordination_tools.initiate_research_workflow(query)
                    )
                    return result
                finally:
                    loop.close()
            except Exception as e:
                logger.error(f"Error in async thread: {e}")
                raise
        
        # Run the async function in a separate thread to avoid event loop conflicts
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_async_in_thread)
            result = future.result(timeout=30)  # 30 second timeout
        
        result_data = json.loads(result)
        
        if result_data.get("success"):
            workflow_id = result_data.get("workflow_id")
            
            # Return information about the delegated research
            response = {
                "delegation_success": True,
                "workflow_id": workflow_id,
                "message": f"Delegated research to multi-agent system: {query}",
                "next_steps": "Use check_multi_agent_workflow_status to monitor progress",
                "note": "The multi-agent system will coordinate specialized agents for comprehensive research",
            }
        else:
            response = {
                "delegation_success": False,
                "error": result_data.get("error", "Unknown error"),
                "message": "Failed to delegate to multi-agent system",
                "fallback": "Proceeding with single-agent research",
            }
        
        logger.info(f"Delegation result for query '{query}': {response['delegation_success']}")
        return json.dumps(response, indent=2)
        
    except Exception as e:
        error_response = {
            "delegation_success": False,
            "error": str(e),
            "message": "Exception occurred during delegation",
            "fallback": "Proceeding with single-agent research",
        }
        logger.error(f"Failed to delegate research: {e}")
        return json.dumps(error_response, indent=2)


def check_multi_agent_workflow_status(workflow_id: str) -> str:
    """
    Check the status of a multi-agent research workflow.
    
    Args:
        workflow_id: The ID of the workflow to check
        
    Returns:
        JSON string with workflow status information
    """
    try:
        import asyncio
        import concurrent.futures
        
        def run_async_in_thread():
            """Run the async function in a separate thread with its own event loop."""
            try:
                # Create a new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        _coordination_tools.get_workflow_status(workflow_id)
                    )
                    return result
                finally:
                    loop.close()
            except Exception as e:
                logger.error(f"Error in async thread: {e}")
                raise
        
        # Run the async function in a separate thread to avoid event loop conflicts
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_async_in_thread)
            result = future.result(timeout=30)  # 30 second timeout
        
        logger.info(f"Retrieved status for workflow {workflow_id}")
        return result
        
    except Exception as e:
        error_response = {
            "success": False,
            "error": str(e),
            "workflow_id": workflow_id,
            "message": "Failed to get workflow status",
        }
        logger.error(f"Failed to get workflow status: {e}")
        return json.dumps(error_response, indent=2)


def get_multi_agent_capabilities() -> str:
    """
    Get information about multi-agent research capabilities.
    
    Returns:
        Information about when and how to use the multi-agent system
    """
    capabilities = """
    # Multi-Agent Research System Capabilities

    ## When to Use Multi-Agent Research
    The multi-agent system is designed for complex research queries that benefit from:
    - **Query Decomposition**: Breaking down complex topics into manageable sub-queries
    - **Parallel Research**: Simultaneous web and social media research
    - **Specialized Analysis**: Dedicated source credibility and cross-reference verification
    - **Comprehensive Synthesis**: Integration of findings from multiple specialized agents

    ## Recommended Use Cases
    - Complex topics requiring multiple research domains
    - Queries that need both academic and social perspective analysis
    - Research requiring extensive source verification and credibility assessment
    - Topics where comprehensive synthesis of diverse findings is critical

    ## Multi-Agent Workflow Phases
    1. **Decomposition**: Query breakdown by Query Decomposition Agent
    2. **Research**: Parallel execution by Web Research and Social Research Agents
    3. **Analysis**: Source analysis and verification by Analysis Agent
    4. **Synthesis**: Final report generation by Synthesis Agent

    ## Alternative: Single-Agent Research
    For simpler queries or when rapid results are needed, continue with standard
    single-agent research using the available web and social research tools.
    """
    
    return capabilities.strip()
