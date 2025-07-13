"""
Enhanced sentiment analysis tools for the Deep Research Agent.

This module provides LLM-based sentiment analysis for text content like Reddit comments.
"""

import logging
from typing import Any

from tools.reddit import RedditComment
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


async def analyze_sentiment_with_llm(
    text: str, context: str | None = None
) -> dict[str, Any]:
    """
    Analyze sentiment of text using LLM.

    Args:
        text (str): The text to analyze
        context (Optional[str]): Optional context about the text source

    Returns:
        Dict[str, Any]: Sentiment analysis results
    """
    # Prepare the prompt
    prompt = "Analyze the sentiment of the following text"
    if context:
        prompt += f" (Context: {context})"
    prompt += f":\n\n{text}\n\nProvide a detailed sentiment analysis."

    try:
        # Generate completion with sentiment analysis
        response = await generate_completion(
            prompt=prompt,
            system=SENTIMENT_SYSTEM_PROMPT,
            think=False,
            model_name="sentiment_analysis",
        )

        # Extract JSON-like response using string manipulation
        # In a production system, we would use more robust parsing
        import json
        import re

        # Try to find JSON in the response
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group(0))
                # Ensure all expected keys are present
                required_keys = [
                    "sentiment",
                    "emotional_tones",
                    "consensus_level",
                    "key_topics",
                    "confidence_level",
                    "brief_summary",
                ]
                for key in required_keys:
                    if key not in result:
                        result[key] = "Not provided"
                return result
            except json.JSONDecodeError:
                logger.warning("Could not parse JSON from LLM response")

        # Fallback if JSON parsing fails
        return {
            "sentiment": "Neutral",
            "emotional_tones": [],
            "consensus_level": "Unknown",
            "key_topics": [],
            "confidence_level": "Low",
            "brief_summary": response[:100] + "...",
            "raw_response": response,
        }
    except Exception as e:
        logger.error(f"Error in sentiment analysis: {e}")
        return {
            "sentiment": "Error",
            "emotional_tones": [],
            "consensus_level": "Error",
            "key_topics": [],
            "confidence_level": "None",
            "brief_summary": f"Error analyzing sentiment: {str(e)}",
        }


async def analyze_reddit_comments_sentiment(
    comments: list[RedditComment],
) -> dict[str, Any]:
    """
    Analyze sentiment and consensus in Reddit comments using LLM.

    Args:
        comments (List[RedditComment]): The comments to analyze

    Returns:
        Dict[str, Any]: LLM-based sentiment analysis results
    """
    if not comments:
        return {
            "sentiment": "Neutral",
            "emotional_tones": [],
            "consensus_level": "No comments",
            "key_topics": [],
            "confidence_level": "None",
            "brief_summary": "No comments to analyze",
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
    result = await analyze_sentiment_with_llm(comments_text, context)

    # Add some Reddit-specific metrics
    result["total_comments_analyzed"] = len(comments)
    result["top_comment_score"] = (
        max(comment.score for comment in comments) if comments else 0
    )
    result["average_comment_score"] = (
        sum(comment.score for comment in comments) / len(comments) if comments else 0
    )

    return result
