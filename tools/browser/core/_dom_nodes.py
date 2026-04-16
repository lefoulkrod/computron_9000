"""Structured DOM node data model.

Represents the output of the JS DOM walker as typed Python objects,
enabling Python-side filtering, rendering, and budget management.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class NodeType(Enum):
    """Type of DOM node emitted by the structured JS walker."""

    TEXT = "text"
    HEADING = "heading"
    INTERACTIVE = "interactive"
    IMAGE = "image"
    CONTAINER_START = "container_start"
    CONTAINER_END = "container_end"
    CHALLENGE = "challenge"


class ViewportPosition(Enum):
    """Whether a node is inside, outside, or partially clipped by the viewport."""

    IN = "in"
    OUT = "out"
    CLIPPED = "clipped"


@dataclass(slots=True)
class DomNode:
    """Single node from the structured DOM snapshot."""

    type: NodeType
    depth: int
    ref: int | None = None
    role: str | None = None
    name: str | None = None
    text: str | None = None
    value: str | None = None
    level: int | None = None
    tag: str | None = None
    viewport: ViewportPosition = ViewportPosition.IN
    expanded: bool | None = None
    selected: bool | None = None
    checked: bool | None = None
    pressed: bool | None = None
    extra: dict | None = None
    challenge_type: str | None = None


__all__ = ["DomNode", "NodeType", "ViewportPosition", "parse_nodes"]


def parse_nodes(raw: list[dict]) -> list[DomNode]:
    """Convert raw JS dicts into typed DomNode instances."""
    result: list[DomNode] = []
    for d in raw:
        result.append(DomNode(
            type=NodeType(d["type"]),
            depth=d.get("depth", 0),
            ref=d.get("ref"),
            role=d.get("role"),
            name=d.get("name"),
            text=d.get("text"),
            value=d.get("value"),
            level=d.get("level"),
            tag=d.get("tag"),
            viewport=ViewportPosition(d.get("viewport", "in")),
            expanded=d.get("expanded"),
            selected=d.get("selected"),
            checked=d.get("checked"),
            pressed=d.get("pressed"),
            extra=d.get("extra"),
            challenge_type=d.get("challenge_type"),
        ))
    return result
