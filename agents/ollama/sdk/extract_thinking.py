import re


def split_think_content(text: str) -> tuple[str, str | None]:
    """Splits text into <think>...</think> and non-think parts. Strips only leading/trailing newlines from each part.

    Args:
        text (str): The input string, possibly containing <think>...</think>.

    Returns:
        Tuple[str, Optional[str]]: (main text, thinking text or None)

    """
    match = re.search(r"<think>([\s\S]*?)</think>", text, re.IGNORECASE)
    if match:
        thinking = match.group(1).strip("\n")
        main = (text[: match.start()] + text[match.end() :]).strip("\n")
        return main, thinking
    return text.strip("\n"), None
