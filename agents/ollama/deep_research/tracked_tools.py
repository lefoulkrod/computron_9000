"""
Tool wrappers with source tracking for the Deep Research Agent.

This module wraps standard web tools to automatically track source usage
for citation and credibility assessment.
"""

import logging
import functools
from typing import List, Optional, Dict, Callable, Any, Union, Union

from agents.ollama.deep_research.source_tracker import SourceTracker
from agents.ollama.deep_research.sentiment_analyzer import analyze_reddit_comments_sentiment
from tools.web import (
    search_google, 
    get_webpage, 
    get_webpage_summary,
    get_webpage_summary_sections,
    get_webpage_substring,
    html_find_elements,
    GoogleSearchResults,
    HtmlElementResult,
)
from tools.web.types import ReducedWebpage
from tools.web.summarize import SectionSummary
from tools.reddit import (
    search_reddit,
    get_reddit_comments_tree_shallow,
    RedditSubmission,
    RedditComment,
)

logger = logging.getLogger(__name__)

class TrackedWebTools:
    """
    Class that provides web tools with automatic source tracking.
    """
    
    def __init__(self, source_tracker: SourceTracker):
        """
        Initialize tracked web tools with a source tracker.
        
        Args:
            source_tracker (SourceTracker): The source tracker to use
        """
        self.source_tracker = source_tracker
    
    async def search_google(self, query: str, max_results: int = 5) -> GoogleSearchResults:
        """
        Search Google with automatic source tracking.
        
        Args:
            query (str): The search query
            max_results (int): Maximum number of results to return
            
        Returns:
            GoogleSearchResults: The search results
        """
        results = await search_google(query=query, max_results=max_results)
        # Track each result URL with the query that found it
        for result in results.results:
            self.source_tracker.register_access(
                url=result.link, 
                tool_name="search_google", 
                query=query
            )
        return results
    
    async def get_webpage(self, url: str) -> ReducedWebpage:
        """
        Get webpage content with automatic source tracking.
        
        Args:
            url (str): The URL to fetch
            
        Returns:
            ReducedWebpage: The webpage content
        """
        self.source_tracker.register_access(url=url, tool_name="get_webpage")
        return await get_webpage(url=url)
    
    async def get_webpage_summary(self, url: str) -> str:
        """
        Get webpage summary with automatic source tracking.
        
        Args:
            url (str): The URL to summarize
            
        Returns:
            str: The webpage summary
        """
        self.source_tracker.register_access(url=url, tool_name="get_webpage_summary")
        return await get_webpage_summary(url=url)
    
    async def get_webpage_summary_sections(self, url: str) -> List[SectionSummary]:
        """
        Get webpage section summaries with automatic source tracking.
        
        Args:
            url (str): The URL to summarize
            
        Returns:
            List[SectionSummary]: The section summaries
        """
        self.source_tracker.register_access(url=url, tool_name="get_webpage_summary_sections")
        return await get_webpage_summary_sections(url=url)
    
    async def get_webpage_substring(self, url: str, start: int, end: int) -> str:
        """
        Get webpage substring with automatic source tracking.
        
        Args:
            url (str): The URL to fetch
            start (int): Start index
            end (int): End index
            
        Returns:
            str: The substring
        """
        self.source_tracker.register_access(url=url, tool_name="get_webpage_substring")
        return await get_webpage_substring(url=url, start=start, end=end)
    
    async def html_find_elements(
        self, html: str, tag: Union[str, List[str]], text: Optional[str] = None
    ) -> List[HtmlElementResult]:
        """
        Find HTML elements with automatic source tracking.
        
        Note: This doesn't track a URL directly as it operates on HTML content.
        
        Args:
            html (str): The HTML content
            tag (Union[str, List[str]]): The HTML tag(s) or CSS selector(s) to search for
            text (Optional[str]): Optional text content to match
            
        Returns:
            List[HtmlElementResult]: The matching HTML elements
        """
        # Note: No direct URL to track
        return await html_find_elements(html=html, selectors=tag, text=text)


class TrackedRedditTools:
    """
    Class that provides Reddit tools with automatic source tracking.
    """
    
    def __init__(self, source_tracker: SourceTracker):
        """
        Initialize tracked Reddit tools with a source tracker.
        
        Args:
            source_tracker (SourceTracker): The source tracker to use
        """
        self.source_tracker = source_tracker
    
    async def search_reddit(self, query: str, limit: int = 10) -> List[RedditSubmission]:
        """
        Search Reddit with automatic source tracking.
        
        Args:
            query (str): The search query
            limit (int): Maximum number of results to return
            
        Returns:
            List[RedditSubmission]: The search results
        """
        results = await search_reddit(query=query, limit=limit)
        # Track each result with the query that found it
        for result in results:
            # Use the permalink as the URL for tracking
            url = f"https://www.reddit.com{result.permalink}"
            self.source_tracker.register_access(
                url=url, 
                tool_name="search_reddit", 
                query=query
            )
        return results
    
    async def get_reddit_comments_tree_shallow(self, submission_id: str, limit: int = 10) -> List[RedditComment]:
        """
        Get Reddit comments with automatic source tracking.
        
        Args:
            submission_id (str): The Reddit submission ID
            limit (int): Maximum number of comments to return
            
        Returns:
            List[RedditComment]: The comments
        """
        url = f"https://www.reddit.com/comments/{submission_id}"
        self.source_tracker.register_access(url=url, tool_name="get_reddit_comments_tree_shallow")
        return await get_reddit_comments_tree_shallow(submission_id=submission_id, limit=limit)
    
    async def analyze_reddit_credibility(self, submission: RedditSubmission) -> Dict[str, Any]:
        """
        Analyze the credibility of a Reddit submission.
        
        Args:
            submission (RedditSubmission): The submission to analyze
            
        Returns:
            Dict[str, Any]: Credibility metrics
        """
        # Simple heuristics for Reddit credibility
        score_factor = min(1.0, submission.score / 1000) * 0.3  # 30% weight for score (max 1000)
        comment_factor = min(1.0, submission.num_comments / 100) * 0.3  # 30% weight for comments (max 100)
        
        # Age of post in days (assuming created_utc is Unix timestamp)
        import time
        age_days = (time.time() - submission.created_utc) / 86400
        recency_factor = max(0.0, min(1.0, (30 - age_days) / 30)) * 0.4  # 40% weight for recency (max 30 days)
        
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
        self.source_tracker.register_access(url=url, tool_name="analyze_reddit_credibility")
        
        return {
            "credibility_score": credibility_score,
            "credibility_level": credibility_level,
            "factors": {
                "post_score": submission.score,
                "comment_count": submission.num_comments,
                "post_age_days": age_days,
            }
        }
    
    async def analyze_comment_sentiment(self, comments: List[RedditComment]) -> Dict[str, Any]:
        """
        Analyze sentiment and consensus in Reddit comments using LLM.
        
        This enhanced version uses the LLM to provide nuanced sentiment analysis,
        detecting emotional tones, consensus patterns, and key discussion topics.
        
        Args:
            comments (List[RedditComment]): The comments to analyze
            
        Returns:
            Dict[str, Any]: Advanced sentiment analysis results from the LLM
        """
        # Register access in source tracker (using the first comment as reference)
        if comments:
            url = f"https://www.reddit.com/comments/{comments[0].id}"
            self.source_tracker.register_access(url=url, tool_name="analyze_comment_sentiment")
        
        # Use the LLM-powered sentiment analyzer
        return await analyze_reddit_comments_sentiment(comments)
        
    async def analyze_comment_sentiment_basic(self, comments: List[RedditComment]) -> Dict[str, Any]:
        """
        Analyze sentiment and consensus in Reddit comments using basic heuristics.
        
        This is the original implementation that uses simple score-based heuristics.
        Kept for fallback purposes.
        
        Args:
            comments (List[RedditComment]): The comments to analyze
            
        Returns:
            Dict[str, Any]: Basic sentiment analysis results
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
            self.source_tracker.register_access(url=url, tool_name="analyze_comment_sentiment_basic")
        
        return {
            "sentiment": sentiment,
            "sentiment_score": sentiment_score,
            "consensus_level": consensus_level,
            "top_comment_score": max_score,
            "average_comment_score": avg_score,
            "total_comments_analyzed": len(comments),
            "method": "basic_heuristics"
        }


# Wrapped functions to get tracked tools

def get_tracked_web_tools(source_tracker: SourceTracker) -> Dict[str, Callable]:
    """
    Get a dictionary of web tools with source tracking.
    
    Args:
        source_tracker (SourceTracker): The source tracker to use
        
    Returns:
        Dict[str, Callable]: Dictionary of tracked web tool functions
    """
    tracked_web_tools = TrackedWebTools(source_tracker)
    
    return {
        "search_google": tracked_web_tools.search_google,
        "get_webpage": tracked_web_tools.get_webpage,
        "get_webpage_summary": tracked_web_tools.get_webpage_summary,
        "get_webpage_summary_sections": tracked_web_tools.get_webpage_summary_sections,
        "get_webpage_substring": tracked_web_tools.get_webpage_substring,
        "html_find_elements": tracked_web_tools.html_find_elements,
    }


def get_tracked_reddit_tools(source_tracker: SourceTracker) -> Dict[str, Callable]:
    """
    Get a dictionary of Reddit tools with source tracking.
    
    Args:
        source_tracker (SourceTracker): The source tracker to use
        
    Returns:
        Dict[str, Callable]: Dictionary of tracked Reddit tool functions
    """
    tracked_reddit_tools = TrackedRedditTools(source_tracker)
    
    return {
        "search_reddit": tracked_reddit_tools.search_reddit,
        "get_reddit_comments_tree_shallow": tracked_reddit_tools.get_reddit_comments_tree_shallow,
        "analyze_reddit_credibility": tracked_reddit_tools.analyze_reddit_credibility,
        "analyze_comment_sentiment": tracked_reddit_tools.analyze_comment_sentiment,
        "analyze_comment_sentiment_basic": tracked_reddit_tools.analyze_comment_sentiment_basic,
    }


# Module exports
__all__ = [
    "TrackedWebTools",
    "TrackedRedditTools",
    "get_tracked_web_tools",
    "get_tracked_reddit_tools",
]
