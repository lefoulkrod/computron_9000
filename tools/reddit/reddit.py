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

class RedditComment(BaseModel):
    """
    Pydantic model for serializing Reddit comments.

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
    replies: list["RedditComment"] = []

    class Config:
        arbitrary_types_allowed = True
        orm_mode = True

async def search_reddit(query: str, limit: int = 10) -> list[RedditSubmission]:
    """
    Search Reddit for posts matching the query.

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

async def get_reddit_comments_tree_shallow(submission_id: str, limit: int = 10) -> list[RedditComment]:
    """
    Retrieve the first N top-level comments for a Reddit submission by submission ID.
    This function fetches the top-level comments and their immediate replies,
    but does not recursively fetch deeper replies to keep the tree shallow.

    Args:
        submission_id (str): The Reddit submission ID.
        limit (int): Maximum number of top-level comments to return.

    Returns:
        list[RedditComment]: List of RedditComment objects representing the top-level comments and their immediate replies.
    """
    try:
        async with asyncpraw.Reddit(
            client_id=config.reddit.client_id,
            client_secret=config.reddit.client_secret,
            user_agent=config.reddit.user_agent,
        ) as reddit:
            submission = await reddit.submission(id=submission_id, fetch=False)
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
                            replies=[]
                        )
                        for reply in top_comment.replies
                    ],
                )
                comments_tree.append(comment_obj)
            return comments_tree
    except Exception as exc:
        logger.exception(f"Failed to fetch comments for submission id: {submission_id}")
        raise
