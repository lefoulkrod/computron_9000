"""Interactive REPL for searching Reddit using search_reddit.

Usage:
    From the project root, run:
        PYTHONPATH=. python tests/tools/web/test_reddit_repl.py

This ensures the 'tools' package is available for import.
"""

import asyncio
import logging

from dotenv import load_dotenv

from tools.reddit import (
    RedditSubmission,
    get_reddit_comments,
    search_reddit,
)

# ...existing code...

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


async def main() -> None:
    """Interactive REPL for searching Reddit and viewing comments."""
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
                    # keep this metadata line under the configured line-length
                    meta_line = (
                        f"   Author: {submission.author} | Score: {submission.score} | "
                        f"Comments: {submission.num_comments} | Created: {submission.created_utc}"
                    )
                    print(meta_line)
                    print(f"   Permalink: https://reddit.com{submission.permalink}")
                    max_self_preview = 1000
                    preview = submission.selftext[:max_self_preview]
                    if len(submission.selftext) > max_self_preview:
                        preview += "..."
                    print(f"   Selftext: {preview}")
                    print()
            except Exception:
                # Avoid embedding exception object in the message; logger.exception will
                # include the exception info automatically.
                logger.exception("Error during Reddit search")
                print("Error during Reddit search")
                results = []
                continue
        print(
            "Options: [number] to view comments, 'search' for new search, 'exit' to quit.",
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
                f"Fetching comments for: {submission.title} (r/{submission.subreddit})",
            )
            try:
                # Pass the raw id (backend can also accept URL; id avoids extra parsing)
                comments = await get_reddit_comments(submission.id)
                print(f"Top {len(comments)} top-level comments:")
                for j, comment in enumerate(comments, 1):
                    print(f"{j}. Author: {comment.author} | Score: {comment.score}")
                    max_body = 1000
                    body_preview = comment.body[:max_body]
                    if len(comment.body) > max_body:
                        body_preview += "..."
                    print(f"   {body_preview}")
                    if comment.replies:
                        print(
                            f"   Replies: {len(comment.replies)} (showing first reply)",
                        )
                        reply = comment.replies[0]
                        reply_preview = reply.body[:max_body]
                        if len(reply.body) > max_body:
                            reply_preview += "..."
                        print(f"      ↳ {reply.author}: {reply_preview}")
                    print()
            except Exception as e:
                logger.exception("Error fetching comments")
                print(f"Error: {e}")
        else:
            print("Invalid option. Please enter a number, 'search', or 'exit'.")


if __name__ == "__main__":
    asyncio.run(main())
