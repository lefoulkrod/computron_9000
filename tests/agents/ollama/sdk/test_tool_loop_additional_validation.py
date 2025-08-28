"""Additional validation tests for complex Pydantic types in tool arguments."""

import pytest
from pydantic import BaseModel

from agents.ollama.sdk.tool_loop import _validate_tool_arguments
from tools.web.types import GetWebpageResult, LinkInfo, ReducedWebpage
from tools.reddit.reddit import RedditSubmission, RedditComment
from tools.virtual_computer.models import (
    WriteFileResult, ReadTextResult, GrepMatch, GrepResult,
    MoveCopyResult, DirEntry, DirectoryReadResult, FileReadResult
)
from config import SearchGoogleConfig, WebToolsConfig, ToolsConfig


@pytest.mark.unit
def test_validate_tool_arguments_web_types():
    """
    Test argument validation with web-related Pydantic models.
    """
    def web_tool(result: GetWebpageResult, links: list[LinkInfo]) -> str:
        return f"Processed {result.url} with {len(links)} links"
    
    arguments = {
        "result": {
            "url": "https://example.com",
            "html": "<html><body>Test</body></html>",
            "response_code": 200
        },
        "links": [
            {"href": "https://example.com/page1", "text": "Page 1"},
            {"href": "https://example.com/page2", "text": "Page 2"}
        ]
    }
    
    result = _validate_tool_arguments(web_tool, arguments)
    
    assert isinstance(result["result"], GetWebpageResult)
    assert result["result"].url == "https://example.com"
    assert result["result"].response_code == 200
    assert isinstance(result["links"], list)
    assert len(result["links"]) == 2
    assert isinstance(result["links"][0], LinkInfo)
    assert result["links"][0].href == "https://example.com/page1"


@pytest.mark.unit
def test_validate_tool_arguments_reddit_types():
    """
    Test argument validation with Reddit Pydantic models.
    """
    def reddit_tool(submission: RedditSubmission, comments: list[RedditComment]) -> str:
        return f"Processed {submission.title}"
    
    arguments = {
        "submission": {
            "id": "abc123",
            "title": "Test Post", 
            "selftext": "Test content",
            "url": "https://reddit.com/r/test/comments/abc123/test_post/",
            "author": "testuser",
            "subreddit": "test",
            "score": 42,
            "num_comments": 5,
            "created_utc": 1640995200.0,
            "permalink": "/r/test/comments/abc123/test_post/"
        },
        "comments": [
            {
                "id": "comment1",
                "author": "commenter1",
                "body": "Great post!",
                "score": 10,
                "created_utc": 1641000000.0,
                "replies": []
            }
        ]
    }
    
    result = _validate_tool_arguments(reddit_tool, arguments)
    
    assert isinstance(result["submission"], RedditSubmission)
    assert result["submission"].title == "Test Post"
    assert result["submission"].score == 42
    assert isinstance(result["comments"], list)
    assert len(result["comments"]) == 1
    assert isinstance(result["comments"][0], RedditComment)
    assert result["comments"][0].body == "Great post!"


@pytest.mark.unit
def test_validate_tool_arguments_virtual_computer_complex_types():
    """
    Test argument validation with complex virtual computer result models.
    """
    def file_tool(grep_result: GrepResult, dir_result: DirectoryReadResult) -> str:
        return "Processed files"
    
    arguments = {
        "grep_result": {
            "success": True,
            "matches": [
                {
                    "file_path": "src/main.py",
                    "line_number": 10,
                    "line": "def main():",
                    "start_col": 0,
                    "end_col": 11
                }
            ],
            "truncated": False,
            "searched_files": 5,
            "error": None
        },
        "dir_result": {
            "type": "directory",
            "name": "src",
            "entries": [
                {"name": "main.py", "is_file": True, "is_dir": False},
                {"name": "utils", "is_file": False, "is_dir": True}
            ]
        }
    }
    
    result = _validate_tool_arguments(file_tool, arguments)
    
    assert isinstance(result["grep_result"], GrepResult)
    assert result["grep_result"].success is True
    assert len(result["grep_result"].matches) == 1
    assert isinstance(result["grep_result"].matches[0], GrepMatch)
    assert result["grep_result"].matches[0].file_path == "src/main.py"
    
    assert isinstance(result["dir_result"], DirectoryReadResult)
    assert result["dir_result"].name == "src"
    assert len(result["dir_result"].entries) == 2
    assert isinstance(result["dir_result"].entries[0], DirEntry)
    assert result["dir_result"].entries[0].is_file is True


@pytest.mark.unit
def test_validate_tool_arguments_config_types():
    """
    Test argument validation with configuration Pydantic models.
    """
    def config_tool(tools_config: ToolsConfig, search_config: SearchGoogleConfig) -> str:
        return "Config processed"
    
    arguments = {
        "tools_config": {
            "web": {
                "search_google": {
                    "state_file": "./custom-state.json",
                    "no_save_state": True,
                    "timeout": 8000
                }
            }
        },
        "search_config": {
            "state_file": "./browser.json",
            "no_save_state": False,
            "timeout": 5000
        }
    }
    
    result = _validate_tool_arguments(config_tool, arguments)
    
    assert isinstance(result["tools_config"], ToolsConfig)
    assert isinstance(result["tools_config"].web, WebToolsConfig)
    assert isinstance(result["tools_config"].web.search_google, SearchGoogleConfig)
    assert result["tools_config"].web.search_google.timeout == 8000
    
    assert isinstance(result["search_config"], SearchGoogleConfig)
    assert result["search_config"].state_file == "./browser.json"
    assert result["search_config"].no_save_state is False


@pytest.mark.unit
def test_validate_tool_arguments_union_types():
    """
    Test argument validation with Union types (like ReadResult).
    
    Note: The current validation function doesn't fully support Union types.
    This test demonstrates the current behavior and documents the limitation.
    """
    from tools.virtual_computer.models import ReadResult
    
    def read_tool(result: ReadResult) -> str:
        return f"Read {result.name}"
    
    # Test with FileReadResult - this will pass through as a dict
    # since Union types aren't properly handled yet
    arguments = {
        "result": {
            "type": "file",
            "name": "test.txt",
            "content": "Hello world",
            "encoding": "utf-8"
        }
    }
    
    result = _validate_tool_arguments(read_tool, arguments)
    
    # Union types currently pass through as dicts without validation
    assert isinstance(result["result"], dict)
    assert result["result"]["type"] == "file"
    assert result["result"]["name"] == "test.txt"
    
    # Test with DirectoryReadResult - also passes through as dict
    arguments = {
        "result": {
            "type": "directory", 
            "name": "src",
            "entries": [
                {"name": "main.py", "is_file": True, "is_dir": False}
            ]
        }
    }
    
    result = _validate_tool_arguments(read_tool, arguments)
    
    # Union types currently pass through as dicts without validation
    assert isinstance(result["result"], dict)
    assert result["result"]["type"] == "directory"
    assert result["result"]["name"] == "src"


@pytest.mark.unit
def test_validate_tool_arguments_nested_optional_fields():
    """
    Test argument validation with complex models containing optional fields.
    """
    def result_tool(write_result: WriteFileResult, read_result: ReadTextResult) -> str:
        return "Results processed"
    
    arguments = {
        "write_result": {
            "success": True,
            "file_path": "test.txt",
            "error": None  # Optional field
        },
        "read_result": {
            "success": True,
            "file_path": "data.txt",
            "content": "File content",
            "start": 1,
            "end": 10,
            "total_lines": 20,
            "error": None
        }
    }
    
    result = _validate_tool_arguments(result_tool, arguments)
    
    assert isinstance(result["write_result"], WriteFileResult)
    assert result["write_result"].success is True
    assert result["write_result"].error is None
    
    assert isinstance(result["read_result"], ReadTextResult)
    assert result["read_result"].start == 1
    assert result["read_result"].end == 10
    assert result["read_result"].total_lines == 20


@pytest.mark.unit 
def test_validate_tool_arguments_self_referencing_models():
    """
    Test argument validation with self-referencing models like RedditComment.
    """
    def comment_tool(comment: RedditComment) -> str:
        return f"Processed comment {comment.id}"
    
    # Test nested replies structure
    arguments = {
        "comment": {
            "id": "parent",
            "author": "user1",
            "body": "Parent comment",
            "score": 5,
            "created_utc": 1640995200.0,
            "replies": [
                {
                    "id": "child1",
                    "author": "user2",
                    "body": "Child comment",
                    "score": 2,
                    "created_utc": 1640999800.0,
                    "replies": []
                }
            ]
        }
    }
    
    result = _validate_tool_arguments(comment_tool, arguments)
    
    assert isinstance(result["comment"], RedditComment)
    assert result["comment"].id == "parent"
    assert len(result["comment"].replies) == 1
    assert isinstance(result["comment"].replies[0], RedditComment)
    assert result["comment"].replies[0].id == "child1"
    assert result["comment"].replies[0].body == "Child comment"
