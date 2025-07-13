import pytest

from agents.ollama.sdk.extract_thinking import split_think_content


@pytest.mark.unit
@pytest.mark.parametrize(
    "input_text,expected_main,expected_thinking",
    [
        (
            "<think>Reasoning here</think> Main output.",
            " Main output.",
            "Reasoning here",
        ),
        ("<think>\nStep 1\nStep 2\n</think>\nResult.", "Result.", "Step 1\nStep 2"),
        ("No think tags here.", "No think tags here.", None),
        ("<think>Just thinking</think>", "", "Just thinking"),
        ("Some main text only.", "Some main text only.", None),
        ("<think>abc</think>   trailing text", "   trailing text", "abc"),
    ],
)
def test_extract_thinking(input_text, expected_main, expected_thinking):
    """
    Test extract_thinking for primary <think> tag scenarios.
    """
    main, thinking = split_think_content(input_text)
    assert main == expected_main
    assert thinking == expected_thinking
