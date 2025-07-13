"""
Social research tools and functionality.

This module provides tools for social media and forum research with agent-specific source tracking.
Migrated from tracked_tools.py and sentiment_analyzer.py as part of Phase 3.2 tool migration refactors.
"""

import json
import logging
import time
from typing import Any

from agents.ollama.deep_research.shared.source_tracking import AgentSourceTracker
from tools.reddit import (
    RedditComment,
    RedditSubmission,
    get_reddit_comments_tree_shallow,
    search_reddit,
)
from utils.generate_completion import generate_completion

logger = logging.getLogger(__name__)

# System prompt for sentiment analysis
SENTIMENT_SYSTEM_PROMPT = """
You are an advanced sentiment analysis system. Your task is to analyze the sentiment,
emotional tone, and consensus of text content (such as comments from social media).

Provide your analysis with these components:
1. Overall sentiment (Very Negative, Negative, Slightly Negative, Neutral, Slightly Positive, Positive, Very Positive)
2. Emotional tones present (e.g., anger, happiness, sadness, etc.)
3. Level of consensus if multiple comments are provided (Strong agreement, Moderate agreement, Mixed opinions, Moderate disagreement, Strong disagreement)
4. Key topics or themes discussed
5. Confidence level in your assessment (High, Medium, Low)

Format your response as a JSON object with these keys:
sentiment, emotional_tones, consensus_level, key_topics, confidence_level, and brief_summary.
"""


class SocialResearchTools:
    """
    Social research tools with agent-specific source tracking.
    
    This class provides social media and forum research capabilities for the Social Research Agent,
    migrated from the centralized TrackedRedditTools implementation and sentiment analyzer.
    """

    def __init__(self, source_tracker: AgentSourceTracker):
        """
        Initialize social research tools with an agent-specific source tracker.

        Args:
            source_tracker (AgentSourceTracker): The agent-specific source tracker to use
        """
        self.source_tracker = source_tracker

    async def _analyze_sentiment_with_llm(
        self, text: str, context: str | None = None
    ) -> dict[str, Any]:
        """
        Analyze sentiment of text using LLM.

        Args:
            text (str): The text to analyze
            context (str | None): Optional context about the text source

        Returns:
            dict[str, Any]: Sentiment analysis results
        """
        # Prepare the prompt
        prompt = f"{SENTIMENT_SYSTEM_PROMPT}\n\nAnalyze the sentiment of the following text"
        if context:
            prompt += f" (Context: {context})"
        prompt += f":\n\n{text}\n\nProvide a detailed sentiment analysis."

        try:
            # Use LLM for advanced sentiment analysis
            response = await generate_completion(prompt=prompt)
            
            try:
                result = json.loads(response)
                # Ensure required fields exist
                required_fields = ["sentiment", "emotional_tones", "consensus_level", "key_topics", "confidence_level", "brief_summary"]
                for field in required_fields:
                    if field not in result:
                        result[field] = "Unknown"
                return result
            except json.JSONDecodeError:
                # Fallback if JSON parsing fails
                return {
                    "sentiment": "Neutral",
                    "emotional_tones": ["mixed"],
                    "consensus_level": "Unknown",
                    "key_topics": ["analysis_error"],
                    "confidence_level": "Low",
                    "brief_summary": "Could not parse LLM response for sentiment analysis",
                }

        except Exception as e:
            logger.error(f"Error in LLM sentiment analysis: {e}")
            return {
                "sentiment": "Error",
                "emotional_tones": [],
                "consensus_level": "Error",
                "key_topics": [],
                "confidence_level": "None",
                "brief_summary": f"Error analyzing sentiment: {str(e)}",
            }

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

        if not comments:
            return {
                "sentiment": "Neutral",
                "emotional_tones": [],
                "consensus_level": "No comments",
                "key_topics": [],
                "confidence_level": "None",
                "brief_summary": "No comments to analyze",
                "total_comments_analyzed": 0,
                "top_comment_score": 0,
                "average_comment_score": 0,
            }

        # Prepare text for analysis
        comments_text = "\n\n".join(
            [
                f"Comment (Score: {comment.score}): {comment.body}"
                for comment in comments[:15]  # Limit to top 15 comments for context window
            ]
        )

        # Add context about the source
        context = f"Reddit thread with {len(comments)} comments, analysis of top {min(15, len(comments))} comments"

        # Use LLM for sentiment analysis
        result = await self._analyze_sentiment_with_llm(comments_text, context)

        # Add some Reddit-specific metrics
        result["total_comments_analyzed"] = len(comments)
        result["top_comment_score"] = (
            max(comment.score for comment in comments) if comments else 0
        )
        result["average_comment_score"] = (
            sum(comment.score for comment in comments) / len(comments) if comments else 0
        )

        return result

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
