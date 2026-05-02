"""Pydantic models for the rclone broker's wire types."""

from __future__ import annotations

from pydantic import BaseModel


class DirectoryItem(BaseModel):
    name: str
    size: int
    is_dir: bool
    mod_time: str  # ISO-8601


class AboutInfo(BaseModel):
    total_bytes: int
    used_bytes: int
    free_bytes: int
