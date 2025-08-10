"""REPL for testing the coder_workflow_agent with a prompt string."""

import asyncio

from agents.ollama.coder.coder_agent_workflow import coder_agent_workflow
from logging_config import setup_logging

setup_logging()


async def main():
    prompt = input("Enter a coding task for the coder workflow agent: ")
    print("\n--- Running coder_workflow_agent ---\n")
    async for result in coder_agent_workflow(prompt):
        print(result)


if __name__ == "__main__":
    asyncio.run(main())
