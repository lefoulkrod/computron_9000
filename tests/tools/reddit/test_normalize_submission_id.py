"""Unit tests for Reddit submission id normalization utilities.

Covers raw ids, standard URLs, short links, whitespace handling, and invalid inputs.
"""

import pytest

from tools.reddit.reddit import RedditInputError, normalize_submission_id


@pytest.mark.unit
@pytest.mark.parametrize(
    "identifier,expected",
    [
        ("1nizasb", "1nizasb"),
        (" 1nizasb ", "1nizasb"),
        ("https://www.reddit.com/r/LocalLLM/comments/1nizasb/computron_9000/", "1nizasb"),
        ("https://reddit.com/r/test/comments/1nizasb/title", "1nizasb"),
        ("https://old.reddit.com/r/test/comments/1nizasb/title/", "1nizasb"),
        ("https://redd.it/1nizasb", "1nizasb"),
    ],
)
def test_normalize_submission_id_valid(identifier: str, expected: str) -> None:
    """Test that various valid identifier forms normalize to the base36 id."""
    assert normalize_submission_id(identifier) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "identifier",
    [
        "",  # empty
        "not valid",  # spaces no id
        "https://example.com/abc",  # wrong domain
    "https://www.reddit.com/r/foo/comments/abcd/",  # id too short (4 chars)
    "https://www.reddit.com/r/foo/comments/thisiswayt/",  # id too long (9 chars)
    ],
)
def test_normalize_submission_id_invalid(identifier: str) -> None:
    """Test that invalid identifiers raise RedditInputError."""
    with pytest.raises(RedditInputError):
        normalize_submission_id(identifier)
