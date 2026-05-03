"""E2E test for markdown code block rendering.

Sends prompts that reliably produce fenced code blocks and inline code,
then verifies the rendered output in both the chat view and the agent
activity view.
"""

from playwright.sync_api import Page, expect

from e2e.pages import ChatView, NetworkView

LLM_TIMEOUT = 180_000

CHAT_PROMPT = (
    "Respond with exactly this markdown and nothing else:\n\n"
    "Here is a function:\n\n"
    "```python\ndef hello():\n    return 'world'\n```\n\n"
    "It returns `'world'`."
)

SUBAGENT_PROMPT = (
    "Spawn a sub-agent. The sub-agent's only job is to respond with exactly "
    "this markdown and nothing else:\n\n"
    "```python\ndef hello():\n    return 'world'\n```\n\n"
    "After the sub-agent finishes, say done."
)


def test_code_blocks_render_in_chat(page: Page):
    """Fenced code blocks and inline code render correctly in the chat view."""
    chat = ChatView(page).goto().new_conversation()
    chat.send(CHAT_PROMPT).wait_streaming(timeout=LLM_TIMEOUT)

    msg = page.get_by_test_id("message-assistant").last

    code_blocks = msg.get_by_test_id("code-block")
    expect(code_blocks.first).to_be_visible(timeout=5000)

    python_block = msg.locator("[data-testid='code-block'][data-lang='python']")
    expect(python_block.first).to_be_visible()

    pre_body = python_block.first.locator("pre")
    expect(pre_body).to_contain_text("def hello()")
    expect(pre_body).to_contain_text("return")

    inline_code = msg.get_by_test_id("inline-code")
    expect(inline_code.first).to_be_visible()


def test_code_blocks_render_in_activity_view(page: Page):
    """Code blocks render correctly in the agent activity view."""
    chat = ChatView(page).goto().new_conversation()
    chat.send(SUBAGENT_PROMPT).wait_streaming(timeout=LLM_TIMEOUT)

    network = NetworkView(page)
    expect(network.indicator).to_be_visible(timeout=10_000)
    network.open()

    expect(network.agent_cards.first).to_be_visible(timeout=5000)
    assert network.agent_cards.count() >= 2, (
        "Expected at least 2 agent cards (root + sub-agent)"
    )

    activity = network.select_agent(1)
    expect(activity.root).to_be_visible(timeout=5000)

    code_blocks = activity.root.get_by_test_id("code-block")
    expect(code_blocks.first).to_be_visible(timeout=5000)

    python_block = activity.root.locator("[data-testid='code-block'][data-lang='python']")
    expect(python_block.first).to_be_visible()

    pre_body = python_block.first.locator("pre")
    expect(pre_body).to_contain_text("def hello()")
    expect(pre_body).to_contain_text("return")
