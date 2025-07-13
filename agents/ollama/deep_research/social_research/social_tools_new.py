"""
Social research tools and functionality.

This module provides tools for social media and forum research with agent-specific source tracking.
Migrated from tracked_tools.py as part of Phase 3.2 tool migration refactors.
"""

import logging
import time
from typing import Any

from agents.ollama.deep_research.sentiment_analyzer import (
    analyze_reddit_comments_sentiment,
)
from agents.ollama.deep_research.shared.source_tracking import AgentSourceTracker
from tools.reddit import (
    RedditComment,
    RedditSubmission,
    get_reddit_comments_tree_shallow,
    search_reddit,
)

logger = logging.getLogger(__name__)


class SocialResearchTools:
    """
    Social research tools with agent-specific source tracking.
    
    This class provides social media and forum research capabilities for the Social Research Agent,
    migrated from the centralized TrackedRedditTools implementation.
    """

    def __init__(self, source_tracker: AgentSourceTracker):
        """
        Initialize social research tools with an agent-specific source tracker.

        Args:
            source_tracker (AgentSourceTracker): The agent-specific source tracker to use
        """
        self.source_tracker = source_tracker

    async def search_reddit(
        self, query: str, limit: int = 10
    ) -> list[RedditSubmission]:
        """
        Search Reddit with automatic source tracking.

        Args:
            query (str): The search query
            limit (int): Maximum number of results to return

        Returns:
            list[RedditSubmission]: The search results
        """
        results = await search_reddit(query=query, limit=limit)
        # Track each result with the query that found it
        for result in results:
            # Use the permalink as the URL for tracking
            url = f"https://www.reddit.com{result.permalink}"
            self.source_tracker.register_access(
                url=url, tool_name="search_reddit", query=query
            )
        return results

    async def get_reddit_comments_tree_shallow(
        self, submission_id: str, limit: int = 10
    ) -> list[RedditComment]:
        """
        Get Reddit comments with automatic source tracking.

        Args:
            submission_id (str): The Reddit submission ID
            limit (int): Maximum number of comments to return

        Returns:
            list[RedditComment]: The comments
        """
        url = f"https://www.reddit.com/comments/{submission_id}"
        self.source_tracker.register_access(
            url=url, tool_name="get_reddit_comments_tree_shallow"
        )
        return await get_reddit_comments_tree_shallow(
            submission_id=submission_id, limit=limit
        )

    async def analyze_reddit_credibility(
        self, submission: RedditSubmission
    ) -> dict[str, Any]:
        """
        Analyze the credibility of a Reddit submission.

        Args:
            submission (RedditSubmission): The submission to analyze

        Returns:
            dict[str, Any]: Credibility metrics
        """
        # Simple heuristics for Reddit credibility
        score_factor = (
            min(1.0, submission.score / 1000) * 0.3
        )  # 30% weight for score (max 1000)
        comment_factor = (
            min(1.0, submission.num_comments / 100) * 0.3
        )  # 30% weight for comments (max 100)

        # Age of post in days (assuming created_utc is Unix timestamp)
        age_days = (time.time() - submission.created_utc) / 86400
        recency_factor = (
            max(0.0, min(1.0, (30 - age_days) / 30)) * 0.4
        )  # 40% weight for recency (max 30 days)

        # Calculate overall credibility score (0-1)
        credibility_score = score_factor + comment_factor + recency_factor

        # Determine credibility level
        if credibility_score > 0.8:
            credibility_level = "High"
        elif credibility_score > 0.5:
            credibility_level = "Medium"
        else:
            credibility_level = "Low"

        url = f"https://www.reddit.com{submission.permalink}"
        self.source_tracker.register_access(
            url=url, tool_name="analyze_reddit_credibility"
        )

        return {
            "credibility_score": credibility_score,
            "credibility_level": credibility_level,
            "factors": {
                "post_score": submission.score,
                "comment_count": submission.num_comments,
                "post_age_days": age_days,
            },
        }

    async def analyze_comment_sentiment(
        self, comments: list[RedditComment]
    ) -> dict[str, Any]:
        """
        Analyze sentiment and consensus in Reddit comments using LLM.

        This enhanced version uses the LLM to provide nuanced sentiment analysis,
        detecting emotional tones, consensus patterns, and key discussion topics.

        Args:
            comments (list[RedditComment]): The comments to analyze

        Returns:
            dict[str, Any]: Advanced sentiment analysis results from the LLM
        """
        # Register access in source tracker (using the first comment as reference)
        if comments:
            url = f"https://www.reddit.com/comments/{comments[0].id}"
            self.source_tracker.register_access(
                url=url, tool_name="analyze_comment_sentiment"
            )

        # Use the LLM-powered sentiment analyzer
        return await analyze_reddit_comments_sentiment(comments)

    async def analyze_comment_sentiment_basic(
        self, comments: list[RedditComment]
    ) -> dict[str, Any]:
        """
        Analyze sentiment and consensus in Reddit comments using basic heuristics.

        This is the original implementation that uses simple score-based heuristics.
        Kept for fallback purposes.

        Args:
            comments (list[RedditComment]): The comments to analyze

        Returns:
            dict[str, Any]: Basic sentiment analysis results
        """
        if not comments:
            return {
                "sentiment": "Neutral",
                "sentiment_score": 0,
                "consensus_level": "No comments",
                "top_comment_score": 0,
            }

        # Simple heuristics for sentiment analysis
        total_score = sum(comment.score for comment in comments)
        avg_score = total_score / len(comments)
        max_score = max(comment.score for comment in comments)

        # Determine consensus level based on ratio of top comment score to average
        if not comments or avg_score == 0:
            consensus_level = "No consensus"
        elif max_score / avg_score > 5:
            consensus_level = "Strong consensus"
        elif max_score / avg_score > 2:
            consensus_level = "Moderate consensus"
        else:
            consensus_level = "Diverse opinions"

        # Calculate rough sentiment based on upvotes
        sentiment_score = avg_score / 10  # Normalize

        if sentiment_score > 0.7:
            sentiment = "Very Positive"
        elif sentiment_score > 0.3:
            sentiment = "Positive"
        elif sentiment_score > -0.3:
            sentiment = "Neutral"
        elif sentiment_score > -0.7:
            sentiment = "Negative"
        else:
            sentiment = "Very Negative"

        # Register access in source tracker (using the first comment as reference)
        if comments:
            url = f"https://www.reddit.com/comments/{comments[0].id}"
            self.source_tracker.register_access(
                url=url, tool_name="analyze_comment_sentiment_basic"
            )

        return {
            "sentiment": sentiment,
            "sentiment_score": sentiment_score,
            "consensus_level": consensus_level,
            "top_comment_score": max_score,
            "average_comment_score": avg_score,
            "total_comments_analyzed": len(comments),
            "method": "basic_heuristics",
        }


# Module exports
__all__ = [
    "SocialResearchTools",
]
