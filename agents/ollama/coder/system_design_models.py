"""Data models for structured system design output.

Provides strict Pydantic models that the system designer agent must emit
as pure JSON (no markdown). These objects allow downstream agents (planner,
implementer, tester) to work with strongly typed data instead of parsing
free-form prose.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from utils.pydantic_schema import schema_summary

logger = logging.getLogger(__name__)


class Component(BaseModel):
    """Simplified system component with user stories.

    Keeps only scalar / list-of-string style fields to remain LLM friendly.

    Attributes:
        name: Component identifier (PascalCase or snake_case acceptable).
        summary: One-line description of purpose / responsibility scope.
        responsibilities: List of short responsibility statements (verbs / responsibilities).
        user_stories: Comprehensive list of user stories relevant to this component.
            Use format: "As a <role> I want <goal> so that <reason>".
        depends_on: Names of other components this component depends on.
        paths: List of relative file or directory paths (from project_structure.path values)
            that this component primarily owns / implements. Each component MUST reference at
            least one path. This creates an explicit mapping so the planner can group
            implementation steps coherently.
    """

    name: str
    summary: str
    responsibilities: list[str] = Field(default_factory=list)
    user_stories: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    paths: list[str] = Field(default_factory=list)

    class Config:
        """Pydantic configuration (forbid extras)."""

        extra = "forbid"


class ProjectStructureNode(BaseModel):
    """Node in a simplified project directory tree.

    Attributes:
        path: Relative path (e.g. "src/app.py", "tests/").
        purpose: Short description of why the path exists (omit if obvious).
    """

    path: str  # relative path (e.g. src/app.py, tests/)
    purpose: str | None = None

    class Config:
        """Pydantic configuration (forbid extras)."""

        extra = "forbid"


class SystemDesign(BaseModel):
    """Top-level system design container.

    Focuses on concise scalar/list shapes amenable to robust LLM generation.

    Attributes:
        summary: One-paragraph plain language overview of the system.
        success_criteria: List of measurable success / acceptance criteria.
        assumptions: List of plain assumption statements (no nesting).
        language: Primary implementation language (optional until chosen).
    dependency_manager: Tool managing project dependencies (e.g. uv, poetry, pnpm).
        packages: List of additional runtime or development packages (frameworks,
            libraries, tools) to include.
        project_structure: Proposed high-level directory/file entries with purposes.
        components: Core components of the architecture (each with comprehensive user stories).
        test_framework: Primary test framework/tool (e.g. pytest, junit, vitest).
    """

    summary: str
    success_criteria: list[str] = Field(default_factory=list)
    # Plain assumption statements (no nested objects)
    assumptions: list[str] = Field(default_factory=list)
    # Explicit primary technology selections
    # Simplified scalar primary selections
    language: str | None = None
    dependency_manager: str | None = None
    packages: list[str] = Field(default_factory=list)
    project_structure: list[ProjectStructureNode] = Field(default_factory=list)
    components: list[Component] = Field(default_factory=list)
    test_framework: str | None = None
    # Removed: data_models, apis, glossary for simplicity

    class Config:
        """Pydantic configuration (forbid extras)."""

        extra = "forbid"


def generate_json_schema() -> dict[str, Any]:  # pragma: no cover - thin wrapper
    """Return full formal JSON Schema for the `SystemDesign` model.

    Uses Pydantic's native schema generation. Not used directly in LLM prompts
    because `$ref` and union constructs can confuse model output, but exported
    for tooling / validation needs.

    Returns:
        A dictionary representing the JSON Schema of `SystemDesign`.
    """
    return SystemDesign.model_json_schema()


def generate_schema_summary() -> str:
    """Generate simplified JSON placeholder shape for `SystemDesign`.

    Uses shared utility to avoid schema drift and duplication. Injects
    curated example literals for select scalar fields via overrides.
    """
    return schema_summary(SystemDesign)
