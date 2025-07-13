"""
Interactive REPL for searching Reddit using search_reddit.

Usage:
    From the project root, run:
        PYTHONPATH=. python tests/tools/web/test_reddit_repl.py

This ensures the 'tools' package is available for import.
"""

import asyncio
import logging

from dotenv import load_dotenv

from tools.reddit import get_reddit_comments_tree_shallow, search_reddit, RedditSubmission

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


async def main() -> None:
    """
    Interactive REPL for searching Reddit and viewing comments.
    """
    print("Reddit Search REPL. Type 'exit' to quit.")
    results: list[RedditSubmission] = []
    while True:
        if not results:
            query = input("Enter search string: ").strip()
            if query.lower() in {"exit", "quit"}:
                print("Exiting.")
                break
            try:
                results = await search_reddit(query)
                print(f"Found {len(results)} results:")
                for i, submission in enumerate(results, 1):
                    print(f"{i}. {submission.title} (r/{submission.subreddit})")
                    print(f"   URL: {submission.url}")
                    print(
                        f"   Author: {submission.author} | Score: {submission.score} | Comments: {submission.num_comments} | Created: {submission.created_utc}"
                    )
                    print(f"   Permalink: https://reddit.com{submission.permalink}")
                    print(
                        f"   Selftext: {submission.selftext[:1000]}{'...' if len(submission.selftext) > 1000 else ''}"
                    )
                    print()
            except Exception as e:
                logger.exception(f"Error during Reddit search: {e}")
                print(f"Error: {e}")
                results = []
                continue
        print(
            "Options: [number] to view comments, 'search' for new search, 'exit' to quit."
        )
        choice = input("Select option: ").strip()
        if choice.lower() in {"exit", "quit"}:
            print("Exiting.")
            break
        if choice.lower() == "search":
            results = []
            continue
        if choice.isdigit() and 1 <= int(choice) <= len(results):
            idx = int(choice) - 1
            submission = results[idx]
            print(
                f"Fetching comments for: {submission.title} (r/{submission.subreddit})"
            )
            try:
                comments = await get_reddit_comments_tree_shallow(submission.url)
                print(f"Top {len(comments)} top-level comments:")
                for j, comment in enumerate(comments, 1):
                    print(f"{j}. Author: {comment.author} | Score: {comment.score}")
                    print(
                        f"   {comment.body[:1000]}{'...' if len(comment.body) > 1000 else ''}"
                    )
                    if comment.replies:
                        print(
                            f"   Replies: {len(comment.replies)} (showing first reply)"
                        )
                        reply = comment.replies[0]
                        print(
                            f"      ↳ {reply.author}: {reply.body[:1000]}{'...' if len(reply.body) > 1000 else ''}"
                        )
                    print()
            except Exception as e:
                logger.exception(f"Error fetching comments: {e}")
                print(f"Error: {e}")
        else:
            print("Invalid option. Please enter a number, 'search', or 'exit'.")


if __name__ == "__main__":
    asyncio.run(main())
