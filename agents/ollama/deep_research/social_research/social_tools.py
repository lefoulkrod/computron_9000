"""
Social research tools and functionality.

This module provides tools for social media and forum research with agent-specific source tracking.
Migrated from tracked_tools.py and sentiment_analyzer.py as part of Phase 3.2 tool migration refactors.
"""

import json
import logging
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

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
        prompt = (
            f"{SENTIMENT_SYSTEM_PROMPT}\n\nAnalyze the sentiment of the following text"
        )
        if context:
            prompt += f" (Context: {context})"
        prompt += f":\n\n{text}\n\nProvide a detailed sentiment analysis."

        try:
            # Use LLM for advanced sentiment analysis
            response = await generate_completion(prompt=prompt)

            try:
                result: dict[str, Any] = json.loads(response)
                # Ensure required fields exist
                required_fields = [
                    "sentiment",
                    "emotional_tones",
                    "consensus_level",
                    "key_topics",
                    "confidence_level",
                    "brief_summary",
                ]
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
                for comment in comments[
                    :15
                ]  # Limit to top 15 comments for context window
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
            sum(comment.score for comment in comments) / len(comments)
            if comments
            else 0
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

    # Citation management functionality for social media sources
    async def generate_reddit_citation(
        self, url: str, style: str = "APA"
    ) -> dict[str, Any]:
        """
        Generate a properly formatted citation for a Reddit source.

        Args:
            url (str): The Reddit URL to generate citation for
            style (str): Citation style (APA, MLA, Chicago)

        Returns:
            Dict[str, Any]: Formatted citation information
        """
        try:
            # Extract Reddit metadata from URL or submission data
            reddit_data = await self._extract_reddit_metadata(url)

            # Format citation based on style
            if style.upper() == "APA":
                citation = self._format_reddit_apa_citation(reddit_data)
            elif style.upper() == "MLA":
                citation = self._format_reddit_mla_citation(reddit_data)
            elif style.upper() == "CHICAGO":
                citation = self._format_reddit_chicago_citation(reddit_data)
            else:
                citation = self._format_reddit_apa_citation(
                    reddit_data
                )  # Default to APA

            return {
                "url": url,
                "style": style,
                "formatted_citation": citation,
                "reddit_data": reddit_data,
                "access_date": datetime.now().strftime("%Y-%m-%d"),
            }
        except Exception as e:
            logger.error(f"Error generating Reddit citation for {url}: {e}")
            return {
                "url": url,
                "style": style,
                "formatted_citation": f"Error generating citation: {str(e)}",
                "reddit_data": {},
                "access_date": datetime.now().strftime("%Y-%m-%d"),
            }

    async def _extract_reddit_metadata(self, url: str) -> dict[str, Any]:
        """Extract metadata from Reddit URL."""
        # Basic Reddit URL parsing

        parsed = urlparse(url)
        path_parts = parsed.path.strip("/").split("/")

        if "comments" in path_parts:
            # Post URL
            try:
                subreddit_idx = path_parts.index("r") + 1
                comments_idx = path_parts.index("comments")
                subreddit = (
                    path_parts[subreddit_idx] if subreddit_idx < len(path_parts) else ""
                )
                post_id = (
                    path_parts[comments_idx + 1]
                    if comments_idx + 1 < len(path_parts)
                    else ""
                )

                return {
                    "type": "post",
                    "subreddit": subreddit,
                    "post_id": post_id,
                    "url": url,
                    "title": "Reddit Post",  # Would need API call to get actual title
                    "author": "Unknown",
                    "date": datetime.now().strftime("%Y, %B %d"),
                }
            except (ValueError, IndexError):
                pass

        return {
            "type": "unknown",
            "subreddit": "",
            "url": url,
            "title": "Reddit Content",
            "author": "Unknown",
            "date": datetime.now().strftime("%Y, %B %d"),
        }

    def _format_reddit_apa_citation(self, reddit_data: dict[str, Any]) -> str:
        """Format Reddit citation in APA style."""
        author = reddit_data.get("author", "Unknown")
        date = reddit_data.get("date", "n.d.")
        title = reddit_data.get("title", "Reddit Post")
        url = reddit_data.get("url", "")

        return f"{author}. ({date}). {title} [Post]. Reddit. {url}"

    def _format_reddit_mla_citation(self, reddit_data: dict[str, Any]) -> str:
        """Format Reddit citation in MLA style."""
        author = reddit_data.get("author", "Unknown")
        title = reddit_data.get("title", "Reddit Post")
        subreddit = reddit_data.get("subreddit", "")
        date = reddit_data.get("date", "")
        url = reddit_data.get("url", "")
        access_date = datetime.now().strftime("%d %b %Y")

        if subreddit:
            return f'{author}. "{title}." Reddit, r/{subreddit}, {date}, {url}. Accessed {access_date}.'
        return f'{author}. "{title}." Reddit, {date}, {url}. Accessed {access_date}.'

    def _format_reddit_chicago_citation(self, reddit_data: dict[str, Any]) -> str:
        """Format Reddit citation in Chicago style."""
        author = reddit_data.get("author", "Unknown")
        title = reddit_data.get("title", "Reddit Post")
        date = reddit_data.get("date", "")
        url = reddit_data.get("url", "")
        access_date = datetime.now().strftime("%B %d, %Y")

        return f'{author}. "{title}." Reddit. {date}. {url} (accessed {access_date}).'

    async def get_social_citation_guidelines(self) -> str:
        """
        Get guidelines for properly citing social media sources.

        Returns:
            str: Citation guidelines for social media platforms
        """
        return """# Citation Guidelines for Social Media Sources

## Reddit Posts

### APA Style
Username. (Year, Month Day). Title of post [Post]. Reddit. URL

### MLA Style
Username. "Title of Post." Reddit, Subreddit Name, Date posted, URL. Accessed Day Month Year.

### Chicago Style
Username. "Title of Post." Reddit. Date posted. URL (accessed Month Day, Year).

## Best Practices for Social Sources
1. Use the actual username, not real name unless publicly known
2. Include subreddit or platform context
3. Note the post type (e.g., [Post], [Comment], [Thread])
4. Always include access date due to potential deletion
5. Consider screenshot capture for important content
6. Evaluate credibility based on community context and user history
"""


# Module exports
__all__ = [
    "SocialResearchTools",
]
