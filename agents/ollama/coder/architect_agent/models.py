"""Pydantic models for low-level design outputs.

This module defines a structured, JSON-serializable schema used to describe a
low-level design (LLD). Each Pydantic model includes Google-style docstrings
documenting its fields to clarify intended usage in generated artifacts and
validations.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from agents.ollama.sdk.schema_tools import model_to_schema

logger = logging.getLogger(__name__)


class Module(BaseModel):
    """A logical component grouping types.

    Args:
        name: Unique module identifier (for example, "core", "entities").
        summary: Short description of the module's responsibility.
    """

    name: str
    summary: str

    class Config:
        """Pydantic configuration (forbid extras)."""

        extra = "forbid"


class InterfaceParam(BaseModel):
    """Parameter specification for an interface.

    Args:
        name: Parameter name as exposed by the interface.
        type: Stringified type annotation for the parameter.
    """

    name: str
    type: str

    class Config:
        """Pydantic configuration (forbid extras)."""

        extra = "forbid"


class InterfaceSpec(BaseModel):
    """Interface exposed by a type.

    Represents a method signature and its behavioral contracts.

    Args:
        name: Interface/method name.
        params: Ordered parameter list for the interface.
        returns: Return type as a string (use "void" when no value is returned).
        raises: Exception type names the operation may raise.
        preconditions: Required truths before invocation.
        postconditions: Truths guaranteed after successful completion.
    """

    name: str
    params: list[InterfaceParam] = Field(default_factory=list)
    returns: str | None = None
    raises: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)

    class Config:
        """Pydantic configuration (forbid extras)."""

        extra = "forbid"


class Attribute(BaseModel):
    """Attribute on a type.

    Args:
        name: Attribute name.
        type: Type name of the attribute.
        mutable: Whether the attribute may change after construction.
        visibility: Visibility level (for example, "private", "protected", "public").
    """

    name: str
    type: str
    mutable: bool
    visibility: str

    class Config:
        """Pydantic configuration (forbid extras)."""

        extra = "forbid"


class FieldSpec(BaseModel):
    """Field for value objects or enums.

    Args:
        name: Field name.
        type: Primitive or referenced type for the field.
    """

    name: str
    type: str

    class Config:
        """Pydantic configuration (forbid extras)."""

        extra = "forbid"


class Member(BaseModel):
    """Unified structural member for a type.

    Args:
        name: Member name.
        type: Member type (primitive or referenced type).
        visibility: Visibility level (for example, "private", "protected", "public").
    """

    name: str
    type: str
    visibility: str

    class Config:
        """Pydantic configuration (forbid extras)."""

        extra = "forbid"


class UsedInterface(BaseModel):
    """Interface usage of another component.

    Args:
        component: The component providing the interface.
        interface: The interface name being used.
        notes: Optional usage notes or rationale.
    """

    component: str
    interface: str
    notes: str | None = None

    class Config:
        """Pydantic configuration (forbid extras)."""

        extra = "forbid"


class TypeSpec(BaseModel):
    """Detailed type definition.

    Args:
        name: Type name (for example, "Game", "Player").
        module: Module in which this type resides.
        stereotype: Kind of type (for example, "class", "entity", "value_object", "enum").
        summary: Concise description of the type's purpose.
        functionality: Comprehensive list of high-level capabilities/responsibilities.
        interfaces: Interfaces (methods) the type exposes.
        members: Unified structural list combining attributes, fields, and literals. Each
            member contains only name, type, and visibility.
        uses_interfaces: External interfaces this type calls.
    """

    name: str
    module: str
    stereotype: str
    summary: str
    functionality: list[str] = Field(default_factory=list)
    interfaces: list[InterfaceSpec] = Field(default_factory=list)
    members: list[Member] = Field(default_factory=list)
    uses_interfaces: list[UsedInterface] = Field(default_factory=list)

    class Config:
        """Pydantic configuration (forbid extras)."""

        extra = "forbid"


class ExceptionSpec(BaseModel):
    """Exception definition.

    Args:
        name: Exception name.
        module: Module where the exception conceptually belongs.
        summary: Human-readable description of the error condition.
    """

    name: str
    module: str
    summary: str

    class Config:
        """Pydantic configuration (forbid extras)."""

        extra = "forbid"


class EnumSpec(BaseModel):
    """Enumeration definition.

    Args:
        name: Enum name.
        module: Module where the enum is defined.
        literals: Allowed values for the enum.
    """

    name: str
    module: str
    literals: list[str] = Field(default_factory=list)

    class Config:
        """Pydantic configuration (forbid extras)."""

        extra = "forbid"


class InteractionStep(BaseModel):
    """Single step in an interaction sequence.

    Args:
        from_: Source "component.operation" of the step. Use field name "from" in JSON.
        to: Target "component.operation" of the step.
        note: Short description of the transition or purpose.
    """

    from_: str = Field(alias="from")
    to: str
    note: str

    class Config:
        """Pydantic configuration (forbid extras)."""

        extra = "forbid"
        allow_population_by_field_name = True


class InteractionSpec(BaseModel):
    """Interaction diagram with ordered steps.

    Args:
        name: Interaction name.
        steps: Ordered list of steps in the interaction.
    """

    name: str
    steps: list[InteractionStep] = Field(default_factory=list)

    class Config:
        """Pydantic configuration (forbid extras)."""

        extra = "forbid"


class LowLevelDesign(BaseModel):
    """Top-level low-level design document.

    Args:
        design_id: Stable identifier of the design artifact.
        name: Human-friendly design title.
        modules: Module catalog summarizing responsibilities.
        types: All type specifications in the design.
        exceptions: Exceptional conditions captured as domain errors.
        enums: Enumerations used by the design.
        interactions: Interaction sequences showing runtime behavior.
    """

    design_id: str
    name: str
    modules: list[Module] = Field(default_factory=list)
    types: list[TypeSpec] = Field(default_factory=list)
    exceptions: list[ExceptionSpec] = Field(default_factory=list)
    enums: list[EnumSpec] = Field(default_factory=list)
    interactions: list[InteractionSpec] = Field(default_factory=list)

    class Config:
        """Pydantic configuration (forbid extras)."""

        extra = "forbid"


def generate_json_schema() -> dict[str, Any]:  # pragma: no cover
    """Return full JSON Schema for LowLevelDesign.

    Returns:
        dict[str, Any]: Pydantic-generated JSON Schema for the model.
    """
    return LowLevelDesign.model_json_schema()


def generate_schema_summary() -> str:
    """Return simplified placeholder JSON for prompts and docs.

    Returns:
        str: Minimal JSON example derived from the schema for guidance.
    """
    return model_to_schema(LowLevelDesign)


# Ensure forward references are resolved when using postponed annotations
InterfaceSpec.model_rebuild()
TypeSpec.model_rebuild()
InteractionSpec.model_rebuild()
LowLevelDesign.model_rebuild()


__all__ = [
    "Attribute",
    "EnumSpec",
    "ExceptionSpec",
    "FieldSpec",
    "InteractionSpec",
    "InteractionStep",
    "InterfaceParam",
    "InterfaceSpec",
    "LowLevelDesign",
    "Member",
    "Module",
    "TypeSpec",
    "UsedInterface",
    "generate_json_schema",
    "generate_schema_summary",
]
