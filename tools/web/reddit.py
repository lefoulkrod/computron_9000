"""
Provides tools for interacting with Reddit using PRAW (Python Reddit API Wrapper).
"""
import logging

import asyncpraw
from asyncpraw.models import Submission
from pydantic import BaseModel

from config import load_config

config = load_config()
logger = logging.getLogger(__name__)

class RedditSubmission(BaseModel):
    """
    Pydantic model for serializing Reddit submissions.

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

async def search_reddit(query: str, limit: int = 10) -> list[RedditSubmission]:
    """
    Search Reddit for posts matching the query.

    Args:
        query (str): The search query.
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
        submissions = []
        async for submission in subreddit.search(query, limit=limit):
            submissions.append(
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
            )
        return submissions
