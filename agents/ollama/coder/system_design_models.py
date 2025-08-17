"""Data models for structured system design output.

Provides strict Pydantic models that the system designer agent must emit
as pure JSON (no markdown). These objects allow downstream agents (planner,
implementer, tester) to work with strongly typed data instead of parsing
free-form prose.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel, Field, model_validator

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
        environment_manager: Version/environment manager (e.g. pyenv, nvm, asdf) when applicable.
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
    environment_manager: str | None = None
    packages: list[str] = Field(default_factory=list)
    project_structure: list[ProjectStructureNode] = Field(default_factory=list)
    components: list[Component] = Field(default_factory=list)
    test_framework: str | None = None
    # Removed: data_models, apis, glossary for simplicity

    class Config:
        """Pydantic configuration (forbid extras)."""

        extra = "forbid"

    @model_validator(mode="after")
    def _validate_component_paths(self) -> SystemDesign:
        """Ensure each component declares valid mapped paths.

        Raises:
            ValueError: If a component omits paths or references unknown paths.
        """
        defined_paths = {p.path for p in self.project_structure}
        for comp in self.components:
            if not comp.paths:
                msg = f"Component '{comp.name}' missing required paths mapping"
                raise ValueError(msg)
            unknown = [pt for pt in comp.paths if pt not in defined_paths]
            if unknown:
                msg = (
                    f"Component '{comp.name}' references paths not in project_structure: {unknown}"
                )
                raise ValueError(msg)
        return self


def generate_json_schema() -> dict[str, Any]:  # pragma: no cover - thin wrapper
    """Return full formal JSON Schema for the `SystemDesign` model.

    Uses Pydantic's native schema generation. Not used directly in LLM prompts
    because `$ref` and union constructs can confuse model output, but exported
    for tooling / validation needs.

    Returns:
        A dictionary representing the JSON Schema of `SystemDesign`.
    """
    return SystemDesign.model_json_schema()


type JSONValue = str | int | float | bool | dict[str, "JSONValue"] | list["JSONValue"] | None

PRIMITIVE_PLACEHOLDERS: dict[type[Any], str] = {
    str: "string",
    int: "number",
    float: "number",
    bool: "boolean",
}


def _placeholder_for_type(tp: object) -> JSONValue:
    """Return a stable, LLM-friendly placeholder representation for a type.

    Rules:
        * Scalars -> symbolic string ("string", "number", etc.)
        * Lists of scalars -> ["string", "..."] pattern
        * Lists of models -> list with a single example object (recursively rendered)
        * Optional[T] -> render as T (omit null markers)
        * Nested models -> dict of their fields
    """
    origin = get_origin(tp)

    # Optional[T] -> treat as T
    if origin is None and isinstance(tp, type) and issubclass(tp, BaseModel):
        return _model_shape(tp)

    if origin in (list, list[int].__class__):  # list typing generics
        args = get_args(tp)
        inner = args[0] if args else str
        inner_placeholder = _placeholder_for_type(inner)
        if isinstance(inner_placeholder, str):  # scalar list
            return [inner_placeholder, "..."]
        # object / composite list -> single example element
        return [inner_placeholder]

    # Optional / Union simplification (treat Optionals as underlying type)
    if origin is Union:  # type: ignore[arg-type]
        non_none = [a for a in get_args(tp) if a is not type(None)]
        if non_none:
            return _placeholder_for_type(non_none[0])
        return "string"

    if isinstance(tp, type) and tp in PRIMITIVE_PLACEHOLDERS:
        return PRIMITIVE_PLACEHOLDERS[tp]

    # Fallback
    return "string"


def _model_shape(model_cls: type[BaseModel]) -> dict[str, JSONValue]:
    """Produce ordered placeholder mapping for a model's fields.

    Iterates deterministically in the order Pydantic stores field definitions
    to keep output stable across runs.
    """
    shape: dict[str, JSONValue] = {}
    for name, field in model_cls.model_fields.items():  # type: ignore[attr-defined]
        placeholder = _placeholder_for_type(field.annotation)  # type: ignore[arg-type]
        shape[name] = placeholder
    return shape


@lru_cache(maxsize=1)
def _dynamic_schema_shape() -> dict[str, JSONValue]:
    """Return the dynamic placeholder shape for `SystemDesign` plus tweaks.

    We post-process certain fields to inject example literals mirroring the
    prior hand-maintained schema so existing prompt templates remain stable.
    """
    shape = _model_shape(SystemDesign)

    # Inject curated example literals for key technology selection fields
    if shape.get("language") == "string":
        shape["language"] = "python"
    if shape.get("dependency_manager") == "string":
        shape["dependency_manager"] = "uv"
    if shape.get("environment_manager") == "string":
        shape["environment_manager"] = "pyenv"
    if shape.get("test_framework") == "string":
        shape["test_framework"] = "pytest"

    return shape


def generate_schema_summary() -> str:
    """Generate the simplified JSON shape used in LLM prompts dynamically.

    This intentionally avoids formal JSON Schema constructs (e.g. `$ref`,
    `anyOf`, explicit nullability) in favor of a stable, example-oriented
    placeholder format that large language models reproduce reliably.

    The shape is computed from the Pydantic models to prevent drift when
    fields are added or renamed.

    Returns:
        Canonical multi-line string describing the expected JSON structure.
    """
    # Pretty-print with sorted keys for stability.
    return json.dumps(_dynamic_schema_shape(), indent=4, sort_keys=True)
