"""Provides tools for interacting with Reddit using PRAW (Python Reddit API Wrapper).

Adds convenience helpers for:
    * Searching submissions (``search_reddit``)
    * Fetching a submission (``get_reddit_submission``)
    * Fetching a shallow comment tree (``get_reddit_comments``)

Robust submission id normalization is supported so callers may pass:
    * Raw base36 ids (e.g. ``1nizasb``)
    * Full reddit URLs (old, new, or short) (e.g. ``https://www.reddit.com/r/foo/comments/1nizasb/title/``)
    * Short links (``https://redd.it/1nizasb``)

Public functions accept any of these forms. Invalid inputs raise ``RedditInputError``.
"""

from __future__ import annotations

import logging
import re
from typing import Final

import asyncpraw
from pydantic import BaseModel

from config import load_config

config = load_config()
logger = logging.getLogger(__name__)


class RedditInputError(ValueError):
    """Exception raised for invalid or un-parseable Reddit submission identifiers."""

    def __init__(self, message: str) -> None:
        """Initialize the RedditInputError with a specific message.

        Args:
            message: Human readable description of the input error.
        """
        super().__init__(message)


MIN_ID_LEN: Final[int] = 5
MAX_ID_LEN: Final[int] = 8
_REDDIT_ID_RE: Final[re.Pattern[str]] = re.compile(
    rf"^[0-9a-z]{{{MIN_ID_LEN},{MAX_ID_LEN}}}$",
)  # typical base36 id length
_URL_ID_PATTERNS: Final[list[re.Pattern[str]]] = [
    # Standard permalink structure (old, new, www, etc.)
    re.compile(
        rf"reddit\.com/r/[^/]+/comments/([0-9a-z]{{{MIN_ID_LEN},{MAX_ID_LEN}}})(?:/|$)",
        re.IGNORECASE,
    ),
    # Short form
    re.compile(
        rf"redd\.it/([0-9a-z]{{{MIN_ID_LEN},{MAX_ID_LEN}}})(?:/|$)",
        re.IGNORECASE,
    ),
]


def normalize_submission_id(identifier: str) -> str:
    """Normalize a user-provided identifier (raw id or URL) to a base36 submission id.

    Args:
        identifier: Raw base36 id, full reddit URL, or short URL.

    Returns:
        The base36 submission id usable with PRAW.

    Raises:
        RedditInputError: If the identifier cannot be parsed / validated.
    """
    ident = identifier.strip()
    if not ident:
        msg = "Empty submission identifier provided"
        raise RedditInputError(msg)

    # Direct id
    if _REDDIT_ID_RE.match(ident):
        return ident

    lowered = ident.lower()
    if "reddit.com" in lowered or "redd.it" in lowered:
        for pat in _URL_ID_PATTERNS:
            m = pat.search(lowered)
            if m:
                extracted = m.group(1)
                # Extra defensive length validation (regex already constrains but keep explicit)
                if MIN_ID_LEN <= len(extracted) <= MAX_ID_LEN:
                    return extracted
                msg = (
                    "Extracted submission id has invalid length: "
                    f"{extracted!r} (len={len(extracted)})"
                )
                raise RedditInputError(msg)
    msg = f"Could not extract submission id from input: {identifier!r}"
    raise RedditInputError(msg)


class RedditSubmission(BaseModel):
    """Pydantic model for serializing Reddit submissions.

    Attributes:
        id (str): Submission ID.
        title (str): Submission title.
        selftext (str): Submission body text.
        url (str): Submission URL.
        author (str | None): Author username.
        subreddit (str): Subreddit name.
        score (int): Submission score.
        num_comments (int): Number of comments.
        created_utc (float): UTC timestamp of creation.
        permalink (str): Relative URL to the post.

    """

    id: str
    title: str
    selftext: str
    url: str
    author: str | None
    subreddit: str
    score: int
    num_comments: int
    created_utc: float
    permalink: str


class RedditComment(BaseModel):
    """Pydantic model for serializing Reddit comments.

    Attributes:
        id (str): Comment ID.
        author (str | None): Author username.
        body (str): Comment body text.
        score (int): Comment score.
        created_utc (float): UTC timestamp of creation.
        replies (list["RedditComment"]): List of immediate replies as RedditComment objects.

    """

    id: str
    author: str | None
    body: str
    score: int
    created_utc: float
    replies: list[RedditComment] = []

    class Config:
        """Pydantic configuration for ``RedditComment`` model."""

        arbitrary_types_allowed = True
        from_attributes = True


async def search_reddit(query: str, limit: int = 10) -> list[RedditSubmission]:
    """Search Reddit for posts matching the query.

    Args:
        query (str): Query string supporting Boolean and field operators:
            • AND, OR, NOT    (use uppercase for logical operators)
            • Parentheses ()   (e.g. "(cats OR dogs) AND NOT mice")
            • author:user      (find posts by a specific user)
            • subreddit:name  (search within a specific subreddit)
            • title:"phrase"  (match exact phrase in title)
            • self:true/false (filter text or link posts)
            • selftext:word    (search text within post bodies)
            • flair:tag        (match posts with a specific flair)
            • site:domain      (posts linking to that domain)
            • url:substring    (substring matches in URLs)
        limit (int): Maximum number of results to return.

    Returns:
        list[RedditSubmission]: List of serializable RedditSubmission objects.

    """
    async with asyncpraw.Reddit(
        client_id=config.reddit.client_id,
        client_secret=config.reddit.client_secret,
        user_agent=config.reddit.user_agent,
    ) as reddit:
        subreddit = await reddit.subreddit("all")
        return [
            RedditSubmission(
                id=submission.id,
                title=submission.title,
                selftext=submission.selftext,
                url=submission.url,
                author=str(submission.author) if submission.author else None,
                subreddit=str(submission.subreddit),
                score=submission.score,
                num_comments=submission.num_comments,
                created_utc=submission.created_utc,
                permalink=submission.permalink,
            )
            async for submission in subreddit.search(query, limit=limit)
        ]


async def get_reddit_comments(
    submission_id: str,
    limit: int = 10,
) -> list[RedditComment]:
    """Get a shallow tree of top-level comments (and their direct replies) for a submission.

    Fetches top-level comments sorted by "top" limited to ``limit`` along with each
    comment's immediate replies (one level deep). Deeper reply chains are not traversed
    to keep the returned structure lightweight and fast.

    Args:
        submission_id (str): Reddit submission ID (base36).
        limit (int): Maximum number of top-level comments to fetch.

    """
    try:
        normalized_id = normalize_submission_id(submission_id)
        async with asyncpraw.Reddit(
            client_id=config.reddit.client_id,
            client_secret=config.reddit.client_secret,
            user_agent=config.reddit.user_agent,
        ) as reddit:
            submission = await reddit.submission(id=normalized_id, fetch=False)
            submission.comment_sort = "top"  # Sort comments by top
            submission.comment_limit = limit  # Limit to top N comments
            await submission.load()
            await submission.comments.replace_more(limit=0)
            comments_tree = []
            for top_comment in submission.comments:
                comment_obj = RedditComment(
                    id=top_comment.id,
                    author=str(top_comment.author) if top_comment.author else None,
                    body=top_comment.body,
                    score=top_comment.score,
                    created_utc=top_comment.created_utc,
                    replies=[
                        RedditComment(
                            id=reply.id,
                            author=str(reply.author) if reply.author else None,
                            body=reply.body,
                            score=reply.score,
                            created_utc=reply.created_utc,
                            replies=[],
                        )
                        for reply in top_comment.replies
                    ],
                )
                comments_tree.append(comment_obj)
            return comments_tree
    except RedditInputError:
        # Re-raise after logging at info (not an internal failure)
        logger.info("Invalid submission identifier provided: %s", submission_id)
        raise
    except Exception:  # pragma: no cover - unexpected
        logger.exception(
            "Failed to fetch comments for submission id: %s",
            submission_id,
        )
        raise


async def get_reddit_submission(submission_id: str) -> RedditSubmission:
    """Fetch a single Reddit submission by its ID.

    Args:
        submission_id (str): The Reddit submission ID.

    Returns:
        RedditSubmission: Serializable RedditSubmission object for the post.

    Raises:
        Exception: If fetching the submission fails.
    """
    try:
        normalized_id = normalize_submission_id(submission_id)
        async with asyncpraw.Reddit(
            client_id=config.reddit.client_id,
            client_secret=config.reddit.client_secret,
            user_agent=config.reddit.user_agent,
        ) as reddit:
            submission = await reddit.submission(id=normalized_id, fetch=True)
            return RedditSubmission(
                id=submission.id,
                title=submission.title,
                selftext=submission.selftext,
                url=submission.url,
                author=str(submission.author) if submission.author else None,
                subreddit=str(submission.subreddit),
                score=submission.score,
                num_comments=submission.num_comments,
                created_utc=submission.created_utc,
                permalink=submission.permalink,
            )
    except RedditInputError:
        logger.info("Invalid submission identifier provided: %s", submission_id)
        raise
    except Exception:  # pragma: no cover - unexpected
        logger.exception("Failed to fetch submission with id: %s", submission_id)
        raise
