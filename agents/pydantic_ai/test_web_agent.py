import pytest
from agents.pydantic_ai.web import web_agent, run_web_agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai import RunContext
from config import load_config
from pydantic_ai.usage import Usage

@pytest.mark.asyncio
async def test_run_web_agent_returns_output():
    """
    Test that the web agent returns output for a simple prompt.
    """
    config = load_config()
    ctx = RunContext(
        model=OpenAIModel(
            model_name=config.llm.model,
            provider=OpenAIProvider(base_url="http://localhost:11434/v1"),
        ),
        usage=Usage(),
        prompt=None,
        deps=None
    )
    result = await run_web_agent(ctx, "Summarize the purpose of example.com")
    assert result is not None
    assert isinstance(result, (str, dict))
