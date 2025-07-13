#!/usr/bin/env python3
"""
Demo script showing how the new Pydantic models generate excellent JSON schemas
for tool function documentation.
"""

import json
from agents.ollama.deep_research.coordinator.coordination_tools import (
    WorkflowInitiationResponse,
    WorkflowStatusResponse,
    AgentResultProcessingResponse,
    WorkflowCompletionResponse,
    TaskExecutionResponse,
    ErrorResponse,
)

def main():
    """Demonstrate JSON schema generation for all response models."""
    
    models = [
        ("WorkflowInitiationResponse", WorkflowInitiationResponse),
        ("WorkflowStatusResponse", WorkflowStatusResponse),
        ("AgentResultProcessingResponse", AgentResultProcessingResponse),
        ("WorkflowCompletionResponse", WorkflowCompletionResponse),
        ("TaskExecutionResponse", TaskExecutionResponse),
        ("ErrorResponse", ErrorResponse),
    ]
    
    print("🔧 Pydantic Model JSON Schemas for Agent Tools\n")
    print("=" * 60)
    
    for name, model_class in models:
        print(f"\n📋 {name}:")
        print("-" * 40)
        schema = model_class.model_json_schema()
        print(json.dumps(schema, indent=2))
        print()

if __name__ == "__main__":
    main()
