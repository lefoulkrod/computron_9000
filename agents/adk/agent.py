"""Module containing the top-level SequentialAgent configuration."""

from google.adk.agents import SequentialAgent

from .computron import computron_agent

# root_agent = SequentialAgent(
#     name="root",
#     sub_agents=[computron_agent],
# )

root_agent = computron_agent