"""Integration test: SummarizeStrategy against real Ollama models.

Run with:
    PYTHONPATH=. uv run pytest tests/agents/ollama/sdk/context/test_summarize_integration.py -v -s
"""

import time

import pytest

from sdk.context import ContextStats, ConversationHistory, SummarizeStrategy


def _build_realistic_history() -> ConversationHistory:
    """Build a conversation history that resembles a real browser agent session."""
    return ConversationHistory([
        {"role": "system", "content": "You are a helpful AI assistant with browser tools."},
        # Turn 1: user asks to find laptops
        {"role": "user", "content": "Find me the cheapest gaming laptop on Amazon under $800."},
        {
            "role": "assistant",
            "content": "I'll search Amazon for gaming laptops under $800.",
            "tool_calls": [
                {"function": {"name": "browse_page", "arguments": {"url": "https://amazon.com"}}},
            ],
        },
        {
            "role": "tool",
            "tool_name": "browse_page",
            "content": (
                "[Page: Amazon.com | https://amazon.com | 200]\n"
                "[Viewport: 0-900 of 4500px]\n\n"
                "[1] [searchbox] Search Amazon\n"
                "[2] [button] Go\n"
                "[3] [link] Today's Deals\n"
                "[4] [link] Customer Service\n"
                "[h2] Shop by Category\n"
                "[5] [link] Electronics\n"
                "[6] [link] Computers\n"
                "[7] [link] Home & Kitchen\n"
                "Welcome to Amazon. Free shipping on millions of items."
            ),
        },
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"function": {"name": "fill_field", "arguments": {"ref": "1", "value": "gaming laptop under $800"}}},
            ],
        },
        {
            "role": "tool",
            "tool_name": "fill_field",
            "content": (
                "[Page: Amazon.com | https://amazon.com | 200]\n"
                "[Viewport: 0-900 of 4500px]\n\n"
                "[1] [searchbox] Search Amazon = gaming laptop under $800\n"
                "[2] [button] Go\n"
            ),
        },
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"function": {"name": "click", "arguments": {"ref": "2"}}},
            ],
        },
        {
            "role": "tool",
            "tool_name": "click",
            "content": (
                "[Page: Amazon.com: gaming laptop under $800 | https://amazon.com/s?k=gaming+laptop | 200]\n"
                "[Viewport: 0-900 of 12000px]\n\n"
                "[1] [searchbox] Search Amazon = gaming laptop under $800\n"
                "[2] [button] Go\n"
                "[h2] Results\n"
                "[8] [link] Acer Nitro V 15 Gaming Laptop | 13th Gen Intel Core i5\n"
                "$629.99 · 4.3 out of 5 stars · 1,247 ratings\n"
                "[9] [link] ASUS TUF Gaming A15 (2024) Gaming Laptop, 15.6\" FHD\n"
                "$749.00 · 4.5 out of 5 stars · 892 ratings\n"
                "[10] [link] Lenovo IdeaPad Gaming 3 15 Laptop\n"
                "$599.99 · 4.2 out of 5 stars · 3,451 ratings\n"
                "[11] [link] HP Victus 15 Gaming Laptop, NVIDIA GeForce RTX 4050\n"
                "$699.99 · 4.4 out of 5 stars · 567 ratings\n"
                "[12] [link] MSI Thin GF63 15.6\" FHD Gaming Laptop\n"
                "$549.99 · 4.1 out of 5 stars · 2,103 ratings\n"
            ),
        },
        {
            "role": "assistant",
            "content": (
                "I found several gaming laptops under $800. The cheapest option is the "
                "MSI Thin GF63 at $549.99. Let me check its specs."
            ),
            "tool_calls": [
                {"function": {"name": "click", "arguments": {"ref": "12"}}},
            ],
        },
        {
            "role": "tool",
            "tool_name": "click",
            "content": (
                "[Page: MSI Thin GF63 15.6\" FHD Gaming Laptop | https://amazon.com/dp/B0C7J3TQ1X | 200]\n"
                "[Viewport: 0-900 of 8500px]\n\n"
                "[h1] MSI Thin GF63 15.6\" FHD 144Hz Gaming Laptop\n"
                "$549.99\n"
                "[13] [button] Add to Cart\n"
                "[14] [button] Buy Now\n"
                "Processor: Intel Core i5-12450H\n"
                "Graphics: NVIDIA GeForce RTX 4050\n"
                "RAM: 8GB DDR4\n"
                "Storage: 512GB NVMe SSD\n"
                "Display: 15.6\" FHD 144Hz IPS\n"
                "Battery: Up to 7 hours\n"
                "Weight: 4.1 lbs\n"
                "[h3] Customer Reviews\n"
                "4.1 out of 5 stars · 2,103 global ratings\n"
                "[15] [link] See all reviews\n"
            ),
        },
        {
            "role": "assistant",
            "content": (
                "The cheapest gaming laptop I found on Amazon under $800 is the "
                "**MSI Thin GF63** at **$549.99**. Here are the key specs:\n\n"
                "- **Processor**: Intel Core i5-12450H\n"
                "- **Graphics**: NVIDIA GeForce RTX 4050\n"
                "- **RAM**: 8GB DDR4\n"
                "- **Storage**: 512GB NVMe SSD\n"
                "- **Display**: 15.6\" FHD 144Hz IPS\n"
                "- **Rating**: 4.1/5 from 2,103 reviews\n\n"
                "Other options were the Lenovo IdeaPad Gaming 3 ($599.99), "
                "Acer Nitro V 15 ($629.99), HP Victus 15 ($699.99), "
                "and ASUS TUF Gaming A15 ($749.00)."
            ),
        },
        # Turn 2: user asks a follow-up
        {"role": "user", "content": "Can you check the reviews for any common complaints?"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"function": {"name": "click", "arguments": {"ref": "15"}}},
            ],
        },
        {
            "role": "tool",
            "tool_name": "click",
            "content": (
                "[Page: MSI Thin GF63 Reviews | https://amazon.com/product-reviews/B0C7J3TQ1X | 200]\n"
                "[Viewport: 0-900 of 6000px]\n\n"
                "[h2] Customer Reviews\n"
                "4.1 out of 5 stars · 2,103 ratings\n"
                "[h3] ★★★★★ Great budget gaming laptop\n"
                "By TechGamer on March 1, 2025\n"
                "Excellent value for the price. Runs most games at medium-high settings.\n"
                "[h3] ★★★★ Good but gets hot\n"
                "By LaptopFan on Feb 15, 2025\n"
                "Performance is solid but thermals could be better. Fan gets loud under load.\n"
                "[h3] ★★★ Average build quality\n"
                "By CasualUser on Feb 10, 2025\n"
                "The plastic chassis feels cheap. Screen is decent though.\n"
                "[h3] ★★ Battery life disappointing\n"
                "By MobileGamer on Jan 28, 2025\n"
                "Only getting about 4 hours on battery, not 7 as advertised.\n"
                "[h3] ★★★★★ Best laptop under $600\n"
                "By BudgetKing on Jan 20, 2025\n"
                "Can't beat this for the price. RTX 4050 at this price point is amazing.\n"
            ),
        },
        {
            "role": "assistant",
            "content": (
                "Based on the reviews, here are the common complaints about the MSI Thin GF63:\n\n"
                "1. **Thermal issues** — Fan gets loud under load, laptop runs hot\n"
                "2. **Build quality** — Plastic chassis feels cheap\n"
                "3. **Battery life** — Real-world battery is ~4 hours, not the advertised 7\n\n"
                "Positive points: Great value, solid gaming performance, RTX 4050 at a great price point."
            ),
        },
    ])


_MODELS = [
    "glm-4.7-flash:Q8_0",
    "qwen2.5:3b",
    "gemma2:2b",
]


@pytest.mark.integration
@pytest.mark.parametrize("model", _MODELS)
async def test_summarize_with_real_model(model: str) -> None:
    """Test summarization against a real Ollama model."""
    strategy = SummarizeStrategy(
        threshold=0.75,
        keep_recent=4,
        summary_model=model,
    )
    history = _build_realistic_history()
    original_len = len(history)
    # Fake stats to trigger the strategy
    stats = ContextStats(context_used=96000, context_limit=128000)

    assert strategy.should_apply(history, stats)

    start = time.perf_counter()
    await strategy.apply(history, stats)
    elapsed = time.perf_counter() - start

    # Verify structure: system + pinned first user + summary + 4 recent messages
    assert history.system_message is not None
    assert history.system_message["content"] == "You are a helpful AI assistant with browser tools."

    # First user message is pinned
    assert history.messages[1]["role"] == "user"
    assert "laptop" in history.messages[1]["content"].lower()

    summary_msg = history.messages[2]
    assert summary_msg["role"] == "user"
    assert "summary" in summary_msg["content"].lower()

    # pinned first user + summary + 4 recent
    non_sys = history.non_system_messages
    assert len(non_sys) == 6  # pinned + summary + 4 recent

    # Summary should contain key information from the conversation
    summary_text = summary_msg["content"].lower()

    print(f"\n{'=' * 70}")
    print(f"Model: {model}")
    print(f"Time: {elapsed:.2f}s")
    print(f"Original messages: {original_len}")
    print(f"After compaction: {len(history)}")
    print(f"Summary length: {len(summary_msg['content'])} chars")
    print(f"{'=' * 70}")
    print(summary_msg["content"])
    print(f"{'=' * 70}")

    # Check that key facts survived the summary
    key_facts_found = 0
    key_facts = [
        "laptop" in summary_text or "msi" in summary_text,
        "549" in summary_text or "550" in summary_text or "cheapest" in summary_text,
        "amazon" in summary_text,
        "review" in summary_text or "complaint" in summary_text or "thermal" in summary_text,
    ]
    key_facts_found = sum(key_facts)

    print(f"Key facts preserved: {key_facts_found}/4")
    for i, (found, desc) in enumerate(zip(key_facts, [
        "laptop/MSI mention",
        "$549 price or cheapest",
        "Amazon mention",
        "reviews/complaints mention",
    ])):
        print(f"  {'✓' if found else '✗'} {desc}")

    # At minimum, the summary should mention laptops and the price
    assert key_facts_found >= 2, (
        f"Summary from {model} preserved only {key_facts_found}/4 key facts. "
        f"Summary: {summary_msg['content'][:200]}..."
    )
