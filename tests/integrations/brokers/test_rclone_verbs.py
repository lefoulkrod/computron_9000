"""Unit tests for the rclone broker's verb dispatcher.

Tests path validation, write enforcement, and verb dispatch without
actually running rclone (the _run_rclone method is mocked).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from integrations._rpc import RpcError
from integrations.brokers.rclone_broker._verbs import VerbDispatcher, _validate_remote_path


# --- Path validation ---

@pytest.mark.unit
class TestValidateRemotePath:
    def test_simple_path(self) -> None:
        assert _validate_remote_path("Documents/notes.txt") == "Documents/notes.txt"

    def test_root_path(self) -> None:
        assert _validate_remote_path("") == ""

    def test_nested_path(self) -> None:
        assert _validate_remote_path("a/b/c/file.pdf") == "a/b/c/file.pdf"

    def test_traversal_blocked(self) -> None:
        with pytest.raises(RpcError, match="path traversal"):
            _validate_remote_path("../etc/passwd")

    def test_traversal_in_middle(self) -> None:
        with pytest.raises(RpcError, match="path traversal"):
            _validate_remote_path("a/../b")

    def test_dotdot_alone(self) -> None:
        with pytest.raises(RpcError, match="path traversal"):
            _validate_remote_path("..")


# --- Verb dispatcher ---

@pytest.mark.unit
class TestVerbDispatcher:
    def _make_dispatcher(self, write_allowed: bool = True) -> VerbDispatcher:
        return VerbDispatcher(
            write_allowed=write_allowed,
            downloads_dir=Path("/tmp/test-downloads"),
        )

    @pytest.mark.asyncio
    async def test_unknown_verb_raises(self) -> None:
        d = self._make_dispatcher()
        with pytest.raises(RpcError, match="unknown verb"):
            await d.dispatch("nonexistent", {})

    @pytest.mark.asyncio
    async def test_write_verb_denied_when_read_only(self) -> None:
        d = self._make_dispatcher(write_allowed=False)
        with pytest.raises(RpcError, match="writes disabled"):
            await d.dispatch("delete", {"remote_path": "test.txt"})

    @pytest.mark.asyncio
    async def test_write_verb_allowed_when_write_enabled(self) -> None:
        d = self._make_dispatcher(write_allowed=True)
        d._run_rclone = AsyncMock(return_value=(0, "", ""))
        result = await d.dispatch("mkdir", {"remote_path": "test_dir"})
        assert result == {"created": True}

    @pytest.mark.asyncio
    async def test_read_verb_allowed_when_read_only(self) -> None:
        d = self._make_dispatcher(write_allowed=False)
        d._run_rclone = AsyncMock(return_value=(0, "[]", ""))
        result = await d.dispatch("list_directory", {"path": ""})
        assert "items" in result

    @pytest.mark.asyncio
    async def test_list_directory(self) -> None:
        d = self._make_dispatcher()
        lsjson_output = json.dumps([
            {"Name": "file.txt", "Size": 100, "IsDir": False, "ModTime": "2024-01-01T00:00:00Z"},
            {"Name": "folder", "Size": 0, "IsDir": True, "ModTime": "2024-01-01T00:00:00Z"},
        ])
        d._run_rclone = AsyncMock(return_value=(0, lsjson_output, ""))
        result = await d.dispatch("list_directory", {"path": "Documents"})
        assert len(result["items"]) == 2
        assert result["items"][0]["name"] == "file.txt"
        assert result["items"][1]["is_dir"] is True

    @pytest.mark.asyncio
    async def test_about(self) -> None:
        d = self._make_dispatcher()
        about_output = json.dumps({"total": 1e12, "used": 5e11, "free": 5e11})
        d._run_rclone = AsyncMock(return_value=(0, about_output, ""))
        result = await d.dispatch("about", {})
        assert result["total_bytes"] == 1e12
        assert result["free_bytes"] == 5e11

    @pytest.mark.asyncio
    async def test_search(self) -> None:
        d = self._make_dispatcher()
        search_output = "Documents/notes.txt\nPhotos/vacation.jpg\n"
        d._run_rclone = AsyncMock(return_value=(0, search_output, ""))
        result = await d.dispatch("search", {"pattern": "notes", "path": ""})
        assert result["count"] == 2
        assert "Documents/notes.txt" in result["matches"]

    @pytest.mark.asyncio
    async def test_cat(self) -> None:
        d = self._make_dispatcher()
        d._run_rclone_raw = AsyncMock(return_value=(0, b"hello world", ""))
        result = await d.dispatch("cat", {"remote_path": "test.txt"})
        assert result["encoding"] == "base64"
        assert result["truncated"] is False
        assert result["size"] == 11
        # Round-trip the base64 to verify content is intact
        decoded = base64.b64decode(result["content"])
        assert decoded == b"hello world"

    @pytest.mark.asyncio
    async def test_cat_binary_content(self) -> None:
        """Binary files survive the round-trip without corruption."""
        import base64 as _base64
        d = self._make_dispatcher()
        # Bytes that are invalid UTF-8: 0x80, 0xFF, 0x00
        binary_data = bytes([0x00, 0x80, 0xFF, 0x41, 0x42, 0x43])
        d._run_rclone_raw = AsyncMock(return_value=(0, binary_data, ""))
        result = await d.dispatch("cat", {"remote_path": "binary.bin"})
        assert result["truncated"] is False
        assert result["size"] == 6
        decoded = _base64.b64decode(result["content"])
        assert decoded == binary_data

    @pytest.mark.asyncio
    async def test_size(self) -> None:
        d = self._make_dispatcher()
        size_output = json.dumps({"count": 42, "bytes": 1234567})
        d._run_rclone = AsyncMock(return_value=(0, size_output, ""))
        result = await d.dispatch("size", {"path": "Documents"})
        assert result["count"] == 42
        assert result["bytes"] == 1234567

    @pytest.mark.asyncio
    async def test_delete_file(self) -> None:
        d = self._make_dispatcher()
        d._run_rclone = AsyncMock(return_value=(0, "", ""))
        result = await d.dispatch("delete", {"remote_path": "test.txt"})
        assert result["deleted"] is True

    @pytest.mark.asyncio
    async def test_mkdir(self) -> None:
        d = self._make_dispatcher()
        d._run_rclone = AsyncMock(return_value=(0, "", ""))
        result = await d.dispatch("mkdir", {"remote_path": "new_folder"})
        assert result["created"] is True

    @pytest.mark.asyncio
    async def test_copy_from_remote(self, tmp_path: Path) -> None:
        d = self._make_dispatcher()
        d._run_rclone = AsyncMock(return_value=(0, "", ""))
        downloads = tmp_path / "downloads"
        d._downloads_dir = downloads
        # Create a dummy file so .stat() succeeds after the mocked rclone
        downloads.mkdir(parents=True, exist_ok=True)
        (downloads / "test.txt").write_bytes(b"hello world")
        result = await d.dispatch("copy_from_remote", {"remote_path": "test.txt"})
        assert result["local_path"] == str(downloads / "test.txt")
        assert result["bytes_copied"] == 11

    @pytest.mark.asyncio
    async def test_copy_to_remote(self, tmp_path: Path) -> None:
        d = self._make_dispatcher()
        d._run_rclone = AsyncMock(return_value=(0, "", ""))
        downloads = tmp_path / "downloads"
        d._downloads_dir = downloads
        # Create a local file to upload
        downloads.mkdir(parents=True, exist_ok=True)
        local_file = downloads / "upload.txt"
        local_file.write_bytes(b"upload content")
        result = await d.dispatch("copy_to_remote", {
            "local_path": str(local_file),
            "remote_path": "Documents/upload.txt",
        })
        assert result["bytes_copied"] == 14
        assert result["remote_path"] == "Documents/upload.txt"

    @pytest.mark.asyncio
    async def test_copy_to_remote_rejects_missing_local_file(self) -> None:
        d = self._make_dispatcher()
        d._run_rclone = AsyncMock(return_value=(0, "", ""))
        # Use a path under /home/computron so it passes _validate_local_path
        # but doesn't actually exist
        with pytest.raises(RpcError, match="local file not found"):
            await d.dispatch("copy_to_remote", {
                "local_path": "/home/computron/nonexistent_file_12345.txt",
                "remote_path": "Documents/test.txt",
            })

    @pytest.mark.asyncio
    async def test_move_from_remote(self, tmp_path: Path) -> None:
        d = self._make_dispatcher()
        d._run_rclone = AsyncMock(return_value=(0, "", ""))
        downloads = tmp_path / "downloads"
        d._downloads_dir = downloads
        downloads.mkdir(parents=True, exist_ok=True)
        (downloads / "move_me.txt").write_bytes(b"moved content")
        result = await d.dispatch("move_from_remote", {"remote_path": "move_me.txt"})
        assert result["local_path"] == str(downloads / "move_me.txt")
        assert result["bytes_moved"] == 13

    @pytest.mark.asyncio
    async def test_move_to_remote(self, tmp_path: Path) -> None:
        d = self._make_dispatcher()
        d._run_rclone = AsyncMock(return_value=(0, "", ""))
        downloads = tmp_path / "downloads"
        d._downloads_dir = downloads
        downloads.mkdir(parents=True, exist_ok=True)
        local_file = downloads / "move_upload.txt"
        local_file.write_bytes(b"move upload content")
        result = await d.dispatch("move_to_remote", {
            "local_path": str(local_file),
            "remote_path": "Archive/move_upload.txt",
        })
        assert result["bytes_moved"] == 19
        assert result["remote_path"] == "Archive/move_upload.txt"

    @pytest.mark.asyncio
    async def test_copy_from_remote_with_custom_local_path(self, tmp_path: Path) -> None:
        d = self._make_dispatcher()
        d._run_rclone = AsyncMock(return_value=(0, "", ""))
        downloads = tmp_path / "downloads"
        d._downloads_dir = downloads
        downloads.mkdir(parents=True, exist_ok=True)
        custom_path = downloads / "custom_name.txt"
        custom_path.write_bytes(b"custom content")
        result = await d.dispatch("copy_from_remote", {
            "remote_path": "original.txt",
            "local_path": str(custom_path),
        })
        assert result["local_path"] == str(custom_path)
        assert result["bytes_copied"] == 14

    @pytest.mark.asyncio
    async def test_delete_falls_back_to_purge_for_directory(self) -> None:
        d = self._make_dispatcher()
        # First call returns "is a directory" error, second succeeds
        d._run_rclone = AsyncMock(
            side_effect=[
                (1, "", "Is a directory"),
                (0, "", ""),
            ]
        )
        result = await d.dispatch("delete", {"remote_path": "test_folder"})
        assert result["deleted"] is True

    @pytest.mark.asyncio
    async def test_path_traversal_in_verb(self) -> None:
        d = self._make_dispatcher()
        with pytest.raises(RpcError, match="path traversal"):
            await d.dispatch("list_directory", {"path": "../secret"})

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self) -> None:
        d = self._make_dispatcher()
        with pytest.raises(RpcError, match="required"):
            await d.dispatch("cat", {})  # missing remote_path — _require_str raises

    @pytest.mark.asyncio
    async def test_cat_truncation(self) -> None:
        d = self._make_dispatcher()
        # Return content larger than max_bytes
        big_content = b"x" * 2000
        d._run_rclone_raw = AsyncMock(return_value=(0, big_content, ""))
        result = await d.dispatch("cat", {"remote_path": "big.txt", "max_bytes": 100})
        assert result["truncated"] is True
        assert result["encoding"] == "base64"
        assert result["size"] == 2000
        decoded = base64.b64decode(result["content"])
        assert len(decoded) == 100
        assert decoded == big_content[:100]


# --- Local path validation ---

@pytest.mark.unit
class TestValidateLocalPath:
    def test_downloads_dir_allowed(self, tmp_path: Path) -> None:
        from integrations.brokers.rclone_broker._verbs import _validate_local_path
        downloads = tmp_path / "downloads"
        downloads.mkdir()
        test_file = downloads / "test.txt"
        test_file.write_text("hello")
        result = _validate_local_path(test_file, downloads)
        assert result == test_file.resolve()

    def test_home_dir_allowed(self, tmp_path: Path) -> None:
        from integrations.brokers.rclone_broker._verbs import _validate_local_path
        # /home/computron is in the allowed roots
        home_file = Path("/home/computron/test.txt")
        # We can't actually create this file in tests, but we can test the
        # validation logic by checking the path resolution
        result = _validate_local_path(home_file, Path("/tmp/downloads"))
        assert str(result).startswith("/home/computron")

    def test_path_outside_allowed_dirs_rejected(self, tmp_path: Path) -> None:
        from integrations.brokers.rclone_broker._verbs import _validate_local_path
        from integrations._rpc import RpcError
        downloads = tmp_path / "downloads"
        downloads.mkdir()
        with pytest.raises(RpcError, match="local path not allowed"):
            _validate_local_path(Path("/etc/passwd"), downloads)
